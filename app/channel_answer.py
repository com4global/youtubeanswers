from openai import OpenAI
from app.channel_loader import resolve_channel_id, search_channel_videos
from app.transcript_loader import get_transcript
from app.chunker import chunk_transcript
from app.embeddings import embed
from app.vector_store import add_vectors, search, reset_index
from app.rag_answer import _filter_evidence


client = OpenAI()


def answer_question_across_channels(question: str, channel_urls: list[str]):
    max_channels = 10
    channel_urls = channel_urls[:max_channels]

    for channel_url in channel_urls:
        channel_id = resolve_channel_id(channel_url)
        if not channel_id:
            continue

        reset_index()
        indexed_chunks = 0

        videos = search_channel_videos(channel_id, question, limit=6)
        if not videos:
            continue

        for video in videos:
            transcript = get_transcript(video["video_id"])
            if not transcript:
                continue

            chunks = chunk_transcript(transcript)
            if not chunks:
                continue

            texts = [c["text"] for c in chunks[:8]]
            embeddings = embed(texts)

            add_vectors(
                [e.embedding for e in embeddings],
                [
                    {
                        "video": video["video_id"],
                        "start": c["start"],
                        "end": c["end"],
                        "text": c["text"],
                        "channel_id": channel_id,
                        "channel_url": channel_url
                    }
                    for c in chunks[:8]
                ]
            )

            indexed_chunks += len(chunks)
            if indexed_chunks >= 40:
                break

        if indexed_chunks == 0:
            continue

        q_embedding = embed([question])[0].embedding
        evidence = search(q_embedding, k=6)
        evidence = _filter_evidence(evidence, question)

        if not evidence:
            continue

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
            "source_channel": channel_url,
            "note": "Answer grounded in channel transcript evidence."
        }

    fallback = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Provide a concise and accurate explanation. "
                    "No usable channel transcripts were found."
                )
            },
            {
                "role": "user",
                "content": question
            }
        ]
    )

    return {
        "answer": fallback.choices[0].message.content,
        "proof": [],
        "note": "No usable channel transcripts were found."
    }
