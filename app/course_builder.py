import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Callable

from openai import OpenAI
from app.playlist_loader import fetch_playlist_videos
from app.transcript_loader import get_transcript
from app.whisper_fallback import transcribe_video, whisper_available
from app.chunker import chunk_transcript


client = OpenAI()

COURSE_MODEL = os.getenv("COURSE_LLM_MODEL", "gpt-4o")
SUMMARY_MODEL = os.getenv("COURSE_SUMMARY_MODEL", COURSE_MODEL)
READING_GUIDE_MODEL = os.getenv("COURSE_READING_GUIDE_MODEL", COURSE_MODEL)
QUIZ_MODEL = os.getenv("COURSE_QUIZ_MODEL", COURSE_MODEL)
LLM_TIMEOUT = int(os.getenv("COURSE_LLM_TIMEOUT", "60"))
LLM_RETRIES = int(os.getenv("COURSE_LLM_RETRIES", "2"))


def _safe_json_loads(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes = total // 60
    secs = total % 60
    return f"{minutes:02d}:{secs:02d}"


def _build_video_url(video_id: str) -> str:
    return f"https://youtube.com/watch?v={video_id}"


def _run_with_timeout(fn, timeout_seconds: int):
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(fn)
        return future.result(timeout=timeout_seconds)
    finally:
        pool.shutdown(wait=False)


def _run_llm_with_retries(fn, timeout_seconds: int, retries: int):
    last_error = None
    for attempt in range(retries + 1):
        try:
            return _run_with_timeout(fn, timeout_seconds)
        except TimeoutError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise TimeoutError("LLM call failed")


def _build_title_only_syllabus(video_summaries: list[dict]) -> dict:
    modules = [{"title": f"Module {i}", "objectives": [], "lessons": []} for i in range(1, 4)]
    for idx, v in enumerate(video_summaries):
        module = modules[idx % len(modules)]
        module["lessons"].append({
            "video_id": v["video_id"],
            "title": v["title"],
            "summary": v.get("summary", ""),
            "learning_objectives": [],
            "estimated_minutes": 5,
            "difficulty": "mixed"
        })

    return {
        "course_title": "Course from Playlist",
        "hook": "Structured learning path generated from playlist titles.",
        "difficulty": "mixed",
        "modules": modules
    }


def build_course(
    playlist_url: str,
    on_progress: Callable[[int, str], None] | None = None,
    max_videos: int = 25,
    max_seconds: int | None = None,
    transcript_timeout: int | None = None,
    transcript_retries: int = 0,
    debug: bool = False,
    on_log: Callable[[str], None] | None = None,
    max_no_transcript_checks: int | None = None,
    allow_title_only: bool = True,
    force_title_only: bool = False,
    use_whisper_fallback: bool = False,
    max_whisper_videos: int = 1
) -> dict:
    def _progress(pct: int, message: str):
        if on_progress:
            on_progress(pct, message)

    def _log(message: str):
        if on_log:
            on_log(message)
        if debug:
            print(message)

    _progress(5, "Fetching playlist")
    videos = fetch_playlist_videos(playlist_url, limit=max_videos)
    if not videos:
        raise ValueError("Playlist is empty or could not be fetched")
    _log(f"[course] playlist loaded videos={len(videos)}")

    video_summaries = []
    video_summary_map: dict[str, dict] = {}
    chunks_by_video: dict[str, list[dict]] = {}

    if max_seconds is None:
        max_seconds = int(os.getenv("COURSE_MAX_SECONDS", "90"))
    if transcript_timeout is None:
        transcript_timeout = int(os.getenv("COURSE_TRANSCRIPT_TIMEOUT", "4"))
    if max_no_transcript_checks is None:
        max_no_transcript_checks = int(os.getenv("COURSE_MAX_NO_TRANSCRIPTS", "4"))
    start_time = time.time()
    def _get_transcript_with_timeout(video_id: str):
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(get_transcript, video_id)
            return future.result(timeout=transcript_timeout)
        finally:
            pool.shutdown(wait=False)

    if force_title_only:
        _log("[course] force_title_only enabled; skipping transcripts")
        video_summaries = [
            {
                "video_id": v["video_id"],
                "title": v["title"],
                "summary": "",
                "video_url": _build_video_url(v["video_id"])
            }
            for v in videos
        ]
        chunks_by_video = {}
    else:
        _progress(10, "Loading transcripts")

    no_transcript_count = 0
    whisper_used = 0
    if use_whisper_fallback and not whisper_available():
        _log("[course] whisper disabled (yt-dlp or ffmpeg missing)")
        use_whisper_fallback = False
    for idx, video in enumerate(videos, start=1):
        if force_title_only:
            break
        if time.time() - start_time > max_seconds:
            _progress(40, "Time budget reached; continuing with available transcripts")
            _log("[course] time budget reached; stopping transcript fetch")
            break

        transcript = None
        for attempt in range(transcript_retries + 1):
            try:
                _log(
                    f"[course] transcript fetch start video_id={video['video_id']} "
                    f"attempt={attempt + 1}"
                )
                transcript = _get_transcript_with_timeout(video["video_id"])
                if transcript:
                    _log(f"[course] transcript ok video_id={video['video_id']}")
                    break
            except TimeoutError:
                transcript = None
                _log(
                    f"[course] transcript timeout video_id={video['video_id']} "
                    f"attempt={attempt + 1}"
                )
            except Exception as e:
                transcript = None
                _log(
                    f"[course] transcript error video_id={video['video_id']} "
                    f"attempt={attempt + 1} error={e}"
                )

        if not transcript and use_whisper_fallback and whisper_used < max_whisper_videos:
            _log(f"[course] whisper fallback video_id={video['video_id']}")
            transcript = transcribe_video(video["video_id"], on_log=_log)
            whisper_used += 1
            if not transcript:
                _log(f"[course] whisper failed video_id={video['video_id']}")

        if not transcript:
            no_transcript_count += 1
            _log(f"[course] no transcript video_id={video['video_id']}")
            pct = 10 + int((idx / len(videos)) * 30)
            _progress(pct, f"Checked {idx}/{len(videos)} videos")
            if no_transcript_count >= max_no_transcript_checks and not video_summaries:
                _log("[course] too many missing transcripts; aborting early")
                break
            continue

        chunks = chunk_transcript(transcript)
        if not chunks:
            pct = 10 + int((idx / len(videos)) * 30)
            _progress(pct, f"Checked {idx}/{len(videos)} videos")
            continue

        chunks_by_video[video["video_id"]] = chunks

        chunk_text = "\n".join(c["text"] for c in chunks)
        chunk_text = _truncate(chunk_text, 12000)

        def _summary_call():
            return client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Write a detailed study summary based strictly on the transcript. "
                            "Return 180–260 words plus 6–10 bullet points covering key ideas, "
                            "definitions, formulas, and practical tips. Use plain language and "
                            "include 1–2 common misconceptions if present. Stay faithful to the transcript."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Title: {video['title']}\nTranscript:\n{chunk_text}"
                    }
                ]
            )

        try:
            summary_response = _run_llm_with_retries(_summary_call, LLM_TIMEOUT, LLM_RETRIES)
            summary = summary_response.choices[0].message.content.strip()
        except TimeoutError:
            _log(f"[course] summary timeout video_id={video['video_id']}")
            summary = ""
        except Exception as e:
            _log(f"[course] summary error video_id={video['video_id']} error={e}")
            summary = ""
        summary_payload = {
            "video_id": video["video_id"],
            "title": video["title"],
            "summary": summary,
            "video_url": _build_video_url(video["video_id"])
        }
        video_summaries.append(summary_payload)
        video_summary_map[video["video_id"]] = summary_payload

        pct = 40 + int((idx / len(videos)) * 15)
        _progress(pct, f"Summarized {idx}/{len(videos)} videos")

    if not video_summaries:
        if not allow_title_only:
            raise ValueError("No usable transcripts found in the playlist")

        _log("[course] falling back to title-only syllabus")
        video_summaries = [
            {
                "video_id": v["video_id"],
                "title": v["title"],
                "summary": "",
                "video_url": _build_video_url(v["video_id"])
            }
            for v in videos
        ]
        video_summary_map = {v["video_id"]: v for v in video_summaries}

    _progress(55, "Generating syllabus")
    def _syllabus_call():
        return client.chat.completions.create(
            model=COURSE_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert instructional designer. Create a 3–5 module course "
                        "from the provided video summaries. Use Bloom's Taxonomy verbs for "
                        "learning objectives. Keep JSON valid."
                    )
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "playlist_url": playlist_url,
                        "videos": video_summaries,
                        "required_format": {
                            "course_title": "string",
                            "hook": "string",
                            "difficulty": "beginner|intermediate|advanced|mixed",
                            "modules": [
                                {
                                    "title": "string",
                                    "objectives": ["string"],
                                    "lessons": [
                                        {
                                            "video_id": "string",
                                            "title": "string",
                                            "summary": "string",
                                            "learning_objectives": ["string"],
                                            "estimated_minutes": 0,
                                            "difficulty": "beginner|intermediate|advanced"
                                        }
                                    ]
                                }
                            ]
                        }
                    })
                }
            ]
        )

    try:
        syllabus_response = _run_llm_with_retries(_syllabus_call, LLM_TIMEOUT, LLM_RETRIES)
        syllabus = _safe_json_loads(syllabus_response.choices[0].message.content)
    except TimeoutError:
        _log("[course] syllabus timeout; using title-only syllabus")
        syllabus = _build_title_only_syllabus(video_summaries)
    except Exception as e:
        _log(f"[course] syllabus error; using title-only syllabus error={e}")
        syllabus = _build_title_only_syllabus(video_summaries)

    _progress(70, "Building study materials")
    study_material_count = 0
    total_lessons = 0
    for module in syllabus.get("modules", []):
        for lesson in module.get("lessons", []):
            total_lessons += 1
            video_id = lesson.get("video_id")
            lesson["study_material_markdown"] = ""
            lesson["reading_guide_markdown"] = lesson.get("reading_guide_markdown", "")
            lesson["video_url"] = _build_video_url(video_id) if video_id else ""

            transcript_snippet = ""
            if video_id and video_id in chunks_by_video:
                chunks = chunks_by_video[video_id]
                transcript_snippet = "\n".join(c["text"] for c in chunks)
            transcript_snippet = _truncate(transcript_snippet, 22000)

            summary_fallback = ""
            if not transcript_snippet and video_id in video_summary_map:
                summary_fallback = video_summary_map[video_id].get("summary", "")

            if not transcript_snippet and not summary_fallback:
                continue

            def _study_call():
                source_block = transcript_snippet or summary_fallback
                return client.chat.completions.create(
                    model=READING_GUIDE_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Create textbook-style study material in Markdown based only on the source text. "
                                "Write 900–1400 words, clear headings, short paragraphs, and examples. "
                                "Structure:\n"
                                "# Lesson Overview\n"
                                "## Key Concepts\n"
                                "## Step-by-step Explanation\n"
                                "## Examples or Applications\n"
                                "## Common Pitfalls\n"
                                "## Quick Recap\n"
                                "## Practice Questions (3-5)\n"
                                "Make it feel like a concise book chapter. Do not invent facts beyond the source."
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Lesson title: {lesson.get('title', '')}\n"
                                f"Source text:\n{source_block}"
                            )
                        }
                    ]
                )

            try:
                study_response = _run_llm_with_retries(_study_call, LLM_TIMEOUT, LLM_RETRIES)
                lesson["study_material_markdown"] = study_response.choices[0].message.content.strip()
                if lesson["study_material_markdown"]:
                    study_material_count += 1
            except TimeoutError:
                _log(f"[course] study material timeout video_id={video_id}")
            except Exception as e:
                _log(f"[course] study material error video_id={video_id} error={e}")

    if total_lessons > 0 and study_material_count == 0:
        raise ValueError(
            "No study material generated. Transcripts may be missing. "
            "Install media tools and try again."
        )

    _progress(85, "Generating module quizzes")
    for module in syllabus.get("modules", []):
        module_video_ids = [
            lesson.get("video_id")
            for lesson in module.get("lessons", [])
            if lesson.get("video_id") in chunks_by_video
        ]
        module_text = []
        for vid in module_video_ids:
            module_text.extend(chunks_by_video.get(vid, []))

        if not module_text:
            module["quiz"] = []
            continue

        module_snippet = "\n".join(
            f"[{_format_timestamp(c['start'])}] {c['text']}"
            for c in module_text[:120]
        )
        module_snippet = _truncate(module_snippet, 10000)

        def _quiz_call():
            return client.chat.completions.create(
                model=QUIZ_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Write 5–8 multiple-choice questions based only on "
                            "the provided transcript snippets. Each question must have 4 options, "
                            "one correct answer_index, and a short explanation. Return JSON "
                            "with a top-level key 'quiz'."
                        )
                    },
                    {
                        "role": "user",
                        "content": module_snippet
                    }
                ]
            )

        try:
            quiz_response = _run_llm_with_retries(_quiz_call, LLM_TIMEOUT, LLM_RETRIES)
            quiz = _safe_json_loads(quiz_response.choices[0].message.content).get("quiz", [])
        except TimeoutError:
            _log(f"[course] quiz timeout module={module.get('title', '')}")
            quiz = []
        except Exception as e:
            _log(f"[course] quiz error module={module.get('title', '')} error={e}")
            quiz = []
        module["quiz"] = quiz

    _progress(95, "Finalizing course")
    course_id = uuid.uuid4().hex
    total_minutes = 0
    for module in syllabus.get("modules", []):
        for lesson in module.get("lessons", []):
            try:
                total_minutes += int(lesson.get("estimated_minutes", 0))
            except Exception:
                pass

    for idx, module in enumerate(syllabus.get("modules", []), start=1):
        module["module_id"] = f"module-{idx}"
        for jdx, lesson in enumerate(module.get("lessons", []), start=1):
            lesson["lesson_id"] = f"lesson-{idx}-{jdx}"

    course = {
        "course_id": course_id,
        "course_title": syllabus.get("course_title", ""),
        "hook": syllabus.get("hook", ""),
        "difficulty": syllabus.get("difficulty", "mixed"),
        "estimated_total_minutes": total_minutes,
        "modules": syllabus.get("modules", []),
        "source": {
            "playlist_url": playlist_url,
            "videos_count": len(video_summaries)
        }
    }

    _progress(100, "Done")
    return course
