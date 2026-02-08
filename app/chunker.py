def chunk_transcript(transcript, window_size=30):
    if not transcript or not isinstance(transcript, list):
        return []

    chunks = []
    current_text = []
    start_time = transcript[0].get("start", 0)

    for item in transcript:
        text = item.get("text")
        start = item.get("start")

        if text is None or start is None:
            continue

        current_text.append(text)

        if start - start_time >= window_size:
            chunks.append({
                "text": " ".join(current_text),
                "start": start_time,
                "end": start
            })
            current_text = []
            start_time = start

    if current_text:
        chunks.append({
            "text": " ".join(current_text),
            "start": start_time,
            "end": transcript[-1].get("start", start_time)
        })

    return chunks
