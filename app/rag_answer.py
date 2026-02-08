from app.youtube_search import search_videos
from app.transcript_loader import get_transcript
from app.whisper_fallback import transcribe_video
from app.chunker import chunk_transcript
from app.embeddings import embed
from app.vector_store import add_vectors, search, reset_index
from openai import OpenAI
import re

client = OpenAI()


# -------------------------------------------------
# Helpers (GENERIC – NO DOMAIN ASSUMPTIONS)
# -------------------------------------------------

def is_definition_question(question: str) -> bool:
    q = question.lower().strip()
    return (
        q.startswith("what is")
        or q.startswith("what are")
        or "meaning of" in q
        or "definition of" in q
    )


def build_search_query(question: str) -> str:
    """
    Generic, high-recall YouTube query.
    Works for ANY topic.
    """
    if is_definition_question(question):
        return f"{question} explained in simple terms"

    return f"{question} explained with examples"


def _filter_evidence(evidence: list[dict], question: str) -> list[dict]:
    if not evidence:
        return []

    keywords = set(re.findall(r"\w+", question.lower()))
    filtered = []
    for e in evidence:
        text = (e.get("text") or "").lower()
        video_id = e.get("video")
        start = e.get("start")
        if not text or not video_id or start is None:
            continue
        if any(k in text for k in keywords):
            filtered.append(e)

    return filtered or [
        e for e in evidence
        if e.get("text") and e.get("video") and e.get("start") is not None
    ]


# -------------------------------------------------
# Main RAG function
# -------------------------------------------------

def _build_proof_links_from_videos(videos: list[dict], limit: int = 3) -> list[str]:
    proof = []
    for v in videos[:limit]:
        video_id = v.get("video_id")
        if not video_id:
            continue
        proof.append(f"https://youtube.com/watch?v={video_id}")
    return proof

def answer_question(question: str):
    reset_index()

    search_query = build_search_query(question)

    # Pull more videos to survive caption / audio failures
    videos = search_videos(search_query, min_views=1000, limit=12)

    indexed_chunks = 0

    # -------------------------------------------------
    # VIDEO INGESTION (best-effort, NEVER FAILS)
    # -------------------------------------------------
    for video in videos:
        # Tier 1: captions
        transcript = get_transcript(video["video_id"])

        # Tier 2: Whisper fallback
        if transcript is None:
            transcript = transcribe_video(video["video_id"])

        if not transcript:
            continue

        chunks = chunk_transcript(transcript)
        if not chunks:
            continue

        texts = [c["text"] for c in chunks]
        embeddings = embed(texts)

        add_vectors(
            [e.embedding for e in embeddings],
            [
                {
                    "video": video["video_id"],
                    "start": c["start"],
                    "end": c["end"],
                    "text": c["text"]
                }
                for c in chunks
            ]
        )

        indexed_chunks += len(chunks)

        # Enough material for a solid answer
        if indexed_chunks >= 50:
            break

    # -------------------------------------------------
    # CASE 1: NO USABLE VIDEO CONTENT → SAFE FALLBACK
    # -------------------------------------------------
    if indexed_chunks == 0:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a knowledgeable expert. "
                        "Provide a clear, correct, and neutral explanation. "
                        "This answer is NOT based on video transcripts."
                    )
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
        )

        return {
            "answer": response.choices[0].message.content,
            "proof": _build_proof_links_from_videos(videos),
            "note": (
                "General knowledge fallback used because usable video "
                "transcripts were unavailable."
            )
        }

    # -------------------------------------------------
    # SEMANTIC RETRIEVAL
    # -------------------------------------------------
    q_embedding = embed([question])[0].embedding
    evidence = search(q_embedding, k=6)

    if not evidence:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Provide a concise and accurate explanation. "
                        "Video relevance was limited."
                    )
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
        )

        return {
            "answer": response.choices[0].message.content,
            "proof": _build_proof_links_from_videos(videos),
            "note": "Limited video relevance; general explanation provided."
        }

    # -------------------------------------------------
    # LIGHT RELEVANCE FILTER (GENERIC)
    # -------------------------------------------------
    keywords = set(re.findall(r"\w+", question.lower()))
    filtered = [
        e for e in evidence
        if any(k in e["text"].lower() for k in keywords)
    ]
    if filtered:
        evidence = filtered

    # -------------------------------------------------
    # BUILD CONTEXT FOR LLM
    # -------------------------------------------------
    context = "\n\n".join(
        f"[Video {e['video']} | {int(e['start'])}s]\n{e['text']}"
        for e in evidence
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert assistant. "
                    "Answer the question ONLY using the provided video transcript context. "
                    "Be clear, accurate, and concise."
                )
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}"
            }
        ]
    )

    return {
        "answer": response.choices[0].message.content,
        "proof": [
            f"https://youtube.com/watch?v={e['video']}&t={int(e['start'])}"
            for e in evidence
        ],
        "note": "Answer grounded in video transcript evidence."
    }
