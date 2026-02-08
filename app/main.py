from dotenv import load_dotenv
import os
import io
import shutil
import subprocess
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.rag_answer import answer_question
from app.course_builder import build_course
from app.course_jobs import create_job, update_job, get_job, persist_result
from app.course_export import load_course, build_course_pdf, build_course_pptx, build_export_filenames
from app.channel_answer import answer_question_across_channels
from app.weekly_battlecard import generate_weekly_battlecard
from app.ai_products import (
    load_ai_products,
    maybe_refresh_ai_products,
    sync_ai_products,
    sync_ai_products_zapier,
    sync_ai_products_sources
)
import traceback
from typing import List

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/ask")
def ask(question: str):
    try:
        return answer_question(question)
    except Exception as e:
        # 🔥 This prints the REAL error in terminal
        traceback.print_exc()

        # return readable error instead of silent 500
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/ask-channels")
def ask_channels(
    question: str,
    channels: List[str] = Query(..., description="Up to 10 YouTube channel URLs")
):
    try:
        return answer_question_across_channels(question, channels)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/weekly-battlecard")
def weekly_battlecard(
    channels: List[str] = Query(..., description="Up to 10 YouTube channel URLs"),
    max_videos_per_channel: int = 4
):
    try:
        return generate_weekly_battlecard(channels, max_channels=10, max_videos_per_channel=max_videos_per_channel)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/ai-products")
def get_ai_products(refresh: bool = False, offset: int = 0, limit: int = 50, q: str | None = None):
    try:
        if refresh:
            data = maybe_refresh_ai_products()
        else:
            data = load_ai_products()
        products = data.get("products", [])
        if q:
            needle = q.strip().lower()
            if needle:
                def _match(product: dict) -> bool:
                    hay = " ".join(
                        str(x).lower()
                        for x in [
                            product.get("name"),
                            product.get("summary"),
                            product.get("value_proposition"),
                            product.get("category"),
                            product.get("pricing"),
                            " ".join(product.get("features", []) or []),
                            " ".join(product.get("tags", []) or [])
                        ]
                        if x
                    )
                    return needle in hay
                products = [p for p in products if _match(p)]
        total = len(products)
        start = max(offset, 0)
        end = start + max(min(limit, 200), 1)
        data["products"] = products[start:end]
        data["offset"] = start
        data["limit"] = end - start
        data["total"] = total
        return data
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai-products/sync")
def sync_ai_products_endpoint(offset: int = 0, limit: int = 50):
    try:
        data = sync_ai_products()
        products = data.get("products", [])
        total = len(products)
        start = max(offset, 0)
        end = start + max(min(limit, 200), 1)
        data["products"] = products[start:end]
        data["offset"] = start
        data["limit"] = end - start
        data["total"] = total
        return data
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai-products/sync-zapier")
def sync_ai_products_zapier_endpoint(offset: int = 0, limit: int = 50):
    try:
        data = sync_ai_products_zapier()
        products = data.get("products", [])
        total = len(products)
        start = max(offset, 0)
        end = start + max(min(limit, 200), 1)
        data["products"] = products[start:end]
        data["offset"] = start
        data["limit"] = end - start
        data["total"] = total
        return data
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai-products/sync-sources")
def sync_ai_products_sources_endpoint(offset: int = 0, limit: int = 50):
    try:
        data = sync_ai_products_sources()
        products = data.get("products", [])
        total = len(products)
        start = max(offset, 0)
        end = start + max(min(limit, 200), 1)
        data["products"] = products[start:end]
        data["offset"] = start
        data["limit"] = end - start
        data["total"] = total
        return data
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _run_course_job(job_id: str, playlist_url: str):
    try:
        update_job(job_id, status="running", progress=0, message="Starting")

        def on_progress(pct: int, message: str):
            update_job(job_id, progress=pct, message=message)

        def on_log(message: str):
            update_job(job_id, log=message)

        # Hard-coded config for consistent output
        max_videos = 20
        max_seconds = 1800
        transcript_timeout = 25
        transcript_retries = 2
        max_no_transcript_checks = 16
        allow_title_only = False
        force_title_only = False
        use_whisper_fallback = True
        max_whisper_videos = max_videos

        on_log(
            "[course] config "
            f"max_videos={max_videos} "
            f"max_seconds={max_seconds} "
            f"transcript_timeout={transcript_timeout} "
            f"transcript_retries={transcript_retries} "
            f"max_no_transcript_checks={max_no_transcript_checks} "
            f"use_whisper_fallback={use_whisper_fallback} "
            f"max_whisper_videos={max_whisper_videos}"
        )

        course = build_course(
            playlist_url,
            on_progress=on_progress,
            max_videos=max_videos,
            max_seconds=max_seconds,
            transcript_timeout=transcript_timeout,
            transcript_retries=transcript_retries,
            debug=False,
            on_log=on_log,
            max_no_transcript_checks=max_no_transcript_checks,
            allow_title_only=allow_title_only,
            force_title_only=force_title_only,
            use_whisper_fallback=use_whisper_fallback,
            max_whisper_videos=max_whisper_videos
        )
        update_job(job_id, status="completed", progress=100, message="Completed", result=course)
        persist_result(job_id, course)
    except Exception as e:
        update_job(job_id, status="failed", message=str(e), log=str(e))


@app.post("/course")
def create_course(playlist_url: str, background_tasks: BackgroundTasks):
    job_id = create_job()
    background_tasks.add_task(
        _run_course_job,
        job_id,
        playlist_url
    )
    return {
        "job_id": job_id,
        "status_url": f"/course/{job_id}"
    }


@app.get("/course/{job_id}")
def get_course(job_id: str):
    job = get_job(job_id)
    if job:
        return job

    course = load_course(job_id)
    if not course:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "message": "Loaded from disk",
        "created_at": 0,
        "updated_at": 0,
        "result": course,
        "logs": []
    }


def _version_info(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True
        )
        output = (result.stdout or result.stderr or "").strip()
        return output.splitlines()[0] if output else None
    except Exception:
        return None


@app.get("/diagnostics")
def diagnostics():
    return {
        "yt_dlp_path": shutil.which("yt-dlp"),
        "ffmpeg_path": shutil.which("ffmpeg"),
        "yt_dlp_version": _version_info(["yt-dlp", "--version"]),
        "ffmpeg_version": _version_info(["ffmpeg", "-version"])
    }


@app.get("/course/{job_id}/export/pdf")
def export_course_pdf(job_id: str):
    course = load_course(job_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    pdf_bytes = build_course_pdf(course)
    filename = build_export_filenames(course)["pdf"]
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.get("/course/{job_id}/export/pptx")
def export_course_pptx(job_id: str):
    course = load_course(job_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    pptx_bytes = build_course_pptx(course)
    filename = build_export_filenames(course)["pptx"]
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers
    )
