import json
import os
from datetime import datetime, timezone
import urllib.request
import urllib.parse

from app.openai_client import get_openai_client
from app.channel_loader import (
    resolve_channel_id,
    search_channel_videos,
    search_channel_videos_fallback,
    get_channel_title,
    extract_video_id,
    get_video_info
)
from app.transcript_loader import get_transcript
from app.chunker import chunk_transcript


MODEL = os.getenv("BATTLECARD_LLM_MODEL", "gpt-4o-mini")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _build_video_url(video_id: str, start: int | None = None) -> str:
    if start is None:
        return f"https://youtube.com/watch?v={video_id}"
    return f"https://youtube.com/watch?v={video_id}&t={int(start)}"


def _gather_channel_evidence(channel_url: str, max_videos: int) -> list[dict]:
    channel_id = resolve_channel_id(channel_url)
    if not channel_id:
        return []

    queries = [
        "new feature",
        "announcement",
        "pricing",
        "update",
        "launch"
    ]

    seen = set()
    candidates = []
    for q in queries:
        for v in search_channel_videos(channel_id, q, limit=max_videos):
            vid = v.get("video_id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            candidates.append(v)

    evidence = []
    for v in candidates[:max_videos]:
        transcript = get_transcript(v["video_id"])
        if not transcript:
            continue

        chunks = chunk_transcript(transcript)
        if not chunks:
            continue

        for c in chunks[:6]:
            evidence.append({
                "channel_url": channel_url,
                "video_id": v["video_id"],
                "video_title": v.get("title", ""),
                "start": c.get("start", 0),
                "text": c.get("text", "")
            })

    return evidence


def _channel_url_from_info(info: dict, fallback: str) -> str:
    if isinstance(info, dict):
        channel = info.get("channel")
        if isinstance(channel, dict):
            link = channel.get("link") or channel.get("url")
            if link:
                return link
            channel_id = channel.get("id") or channel.get("channelId")
            if channel_id:
                return f"https://www.youtube.com/channel/{channel_id}"
    return fallback


def _fetch_oembed(video_id: str) -> dict:
    try:
        url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "format": "json"
        })
        with urllib.request.urlopen(url, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _collect_video_evidence(video_id: str, video_title: str, channel_url: str) -> list[dict]:
    transcript = get_transcript(video_id)
    if not transcript:
        return []

    chunks = chunk_transcript(transcript)
    if not chunks:
        return []

    evidence = []
    for c in chunks[:6]:
        evidence.append({
            "channel_url": channel_url,
            "video_id": video_id,
            "video_title": video_title,
            "start": c.get("start", 0),
            "text": c.get("text", "")
        })
    return evidence


def _classify_fallback_items(items: list[dict]) -> dict | None:
    if not items:
        return None

    payload = [
        {
            "title": i.get("title", ""),
            "description": i.get("description", ""),
            "channel_url": i.get("channel_url", ""),
            "video_url": _build_video_url(i.get("video_id"))
        }
        for i in items
    ]

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify competitor update signals from YouTube titles/descriptions only. "
                        "Return low-confidence labels when evidence is thin."
                    )
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "required_format": {
                            "concepts": ["string"],
                            "video_summaries": [
                                {
                                    "video_url": "string",
                                    "title": "string",
                                    "summary": "string",
                                    "confidence": "string"
                                }
                            ],
                            "new_features": [
                                {
                                    "item": "string",
                                    "channel_url": "string",
                                    "video_url": "string",
                                    "confidence": "string"
                                }
                            ],
                            "pricing_changes": [
                                {
                                    "item": "string",
                                    "channel_url": "string",
                                    "video_url": "string",
                                    "confidence": "string"
                                }
                            ],
                            "messaging_shifts": [
                                {
                                    "item": "string",
                                    "channel_url": "string",
                                    "video_url": "string",
                                    "confidence": "string"
                                }
                            ],
                            "sentiment_shift": {
                                "status": "string",
                                "summary": "string",
                                "confidence": "string"
                            }
                        },
                        "items": payload,
                        "note": (
                            "Use only titles/descriptions. If unsure, return empty arrays "
                            "or low confidence. concepts should be key topics."
                        )
                    })
                }
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return None


def generate_weekly_battlecard(channel_urls: list[str], max_channels: int = 10, max_videos_per_channel: int = 4):
    channel_urls = channel_urls[:max_channels]
    all_evidence = []
    fallback_items = []
    for url in channel_urls:
        normalized_url = url
        video_id = extract_video_id(url)
        video_title = ""
        video_description = ""
        video_published = ""
        if video_id:
            info = get_video_info(f"https://www.youtube.com/watch?v={video_id}")
            oembed = _fetch_oembed(video_id)
            normalized_url = _channel_url_from_info(
                info,
                fallback=oembed.get("author_url", "") or url
            )
            video_title = (
                (info.get("title") if isinstance(info, dict) else "")
                or oembed.get("title", "")
            )
            if isinstance(info, dict):
                video_description = info.get("description", "") or ""
                video_published = (
                    info.get("publishDate")
                    or info.get("publishedTime")
                    or info.get("publishDateText")
                    or ""
                )

        channel_id = resolve_channel_id(normalized_url)
        if not channel_id:
            continue
        normalized_url = f"https://www.youtube.com/channel/{channel_id}"

        if video_id:
            all_evidence.extend(_collect_video_evidence(video_id, video_title, normalized_url))
            fallback_items.append({
                "channel_url": normalized_url,
                "video_id": video_id,
                "title": video_title,
                "description": video_description,
                "published": video_published or ""
            })

        channel_title = get_channel_title(channel_id)
        all_evidence.extend(_gather_channel_evidence(normalized_url, max_videos_per_channel))

        # Collect metadata for fallback if transcripts are missing
        if max_videos_per_channel > 0:
            videos = search_channel_videos(channel_id, "announcement", limit=max_videos_per_channel)
            if not videos:
                videos = search_channel_videos_fallback(channel_id, channel_title, limit=max_videos_per_channel)
            for v in videos:
                fallback_items.append({
                    "channel_url": normalized_url,
                    "video_id": v.get("video_id"),
                    "title": v.get("title", ""),
                    "description": v.get("description", ""),
                    "published": v.get("published", "")
                })

    context_lines = []
    for e in all_evidence:
        snippet = _truncate(e["text"], 300)
        context_lines.append(
            f"[Channel {e['channel_url']} | Video {e['video_id']} | {int(e['start'])}s] "
            f"{e['video_title']} — {snippet}"
        )

    context = _truncate("\n".join(context_lines), 8000)
    generated_at = datetime.now(timezone.utc).isoformat()

    if not context_lines and fallback_items:
        fallback_lines = []
        for item in fallback_items:
            snippet = _truncate(item.get("description", ""), 300)
            fallback_lines.append(
                f"[Channel {item['channel_url']} | Video {item['video_id']}] "
                f"{item['title']} ({item.get('published', '')}) — {snippet}"
            )
        context = _truncate("\n".join(fallback_lines), 8000)

    if not context_lines and fallback_items:
        llm_fallback = _classify_fallback_items(fallback_items)
        keyword_map = {
            "pricing_changes": [
                "price", "pricing", "plan", "subscription", "$", "cost",
                "tier", "license", "bundle", "billing", "discount", "promo",
                "trial", "free", "freemium", "paid", "upgrade", "downgrade"
            ],
            "new_features": [
                "feature", "launch", "introduc", "release", "update", "new",
                "announc", "rollout", "beta", "preview", "early access", "ai update",
                "capability", "improvement", "upgrade"
            ],
            "messaging_shifts": [
                "position", "mission", "vision", "strategy", "rebrand", "community",
                "era", "ai updates", "ai update", "gemini", "platform shift",
                "new direction", "we're shifting", "our focus", "our vision",
                "reposition", "next chapter", "future of", "the future"
            ]
        }

        def _match_keywords(text: str, keywords: list[str]) -> bool:
            t = text.lower()
            return any(k in t for k in keywords)

        new_features = []
        pricing_changes = []
        messaging_shifts = []
        concepts = []
        video_summaries = []
        channels_notes = {}

        for item in fallback_items:
            combined = f"{item.get('title', '')} {item.get('description', '')}"
            video_url = _build_video_url(item.get("video_id"))
            if _match_keywords(combined, keyword_map["pricing_changes"]):
                pricing_changes.append({
                    "item": item.get("title", ""),
                    "channel_url": item.get("channel_url", ""),
                    "video_url": video_url,
                    "confidence": "low"
                })
            if _match_keywords(combined, keyword_map["new_features"]):
                new_features.append({
                    "item": item.get("title", ""),
                    "channel_url": item.get("channel_url", ""),
                    "video_url": video_url,
                    "confidence": "low"
                })
            if _match_keywords(combined, keyword_map["messaging_shifts"]):
                messaging_shifts.append({
                    "item": item.get("title", ""),
                    "channel_url": item.get("channel_url", ""),
                    "video_url": video_url,
                    "confidence": "low"
                })

            channel_url = item.get("channel_url", "")
            if channel_url:
                channels_notes[channel_url] = channels_notes.get(channel_url, 0) + 1

        if llm_fallback:
            concepts = llm_fallback.get("concepts") or concepts
            video_summaries = llm_fallback.get("video_summaries") or video_summaries
            new_features = llm_fallback.get("new_features") or new_features
            pricing_changes = llm_fallback.get("pricing_changes") or pricing_changes
            messaging_shifts = llm_fallback.get("messaging_shifts") or messaging_shifts
            sentiment_shift = llm_fallback.get("sentiment_shift") or {
                "status": "unknown",
                "summary": "Insufficient transcript/comment data to assess sentiment shift.",
                "confidence": "low"
            }
        else:
            sentiment_shift = {
                "status": "unknown",
                "summary": "Insufficient transcript/comment data to assess sentiment shift.",
                "confidence": "low"
            }

        for bucket in (new_features, pricing_changes, messaging_shifts):
            for item in bucket:
                if "confidence" not in item:
                    item["confidence"] = "low"

        if not new_features and not pricing_changes and not messaging_shifts:
            for item in fallback_items[:5]:
                video_url = _build_video_url(item.get("video_id"))
                new_features.append({
                    "item": item.get("title", "") or "Recent video (title unavailable)",
                    "channel_url": item.get("channel_url", ""),
                    "video_url": video_url,
                    "confidence": "low"
                })

        if not video_summaries:
            seen_video_urls = set()
            for item in fallback_items[:5]:
                video_url = _build_video_url(item.get("video_id"))
                if not video_url or video_url in seen_video_urls:
                    continue
                seen_video_urls.add(video_url)
                summary = (item.get("description", "") or item.get("title", "")).strip()
                if not summary:
                    summary = "Summary unavailable from title/description."
                video_summaries.append({
                    "video_url": video_url,
                    "title": item.get("title", "") or "Title unavailable",
                    "summary": summary,
                    "confidence": "low"
                })

        for item in fallback_items:
            title = item.get("title", "")
            if title and title not in concepts:
                concepts.append(title)
            if len(concepts) >= 8:
                break

        return {
            "generated_at": generated_at,
            "battlecard": {
                "summary": "Generated from video titles/descriptions due to missing transcripts.",
                "concepts": concepts,
                "video_summaries": video_summaries,
                "new_features": new_features,
                "pricing_changes": pricing_changes,
                "messaging_shifts": messaging_shifts,
                "sentiment_shift": sentiment_shift,
                "channels": [
                    {
                        "channel_url": k,
                        "notes": f"{v} recent videos scanned."
                    }
                    for k, v in channels_notes.items()
                ]
            },
            "evidence": [
                {
                    "channel_url": item.get("channel_url"),
                    "video_url": _build_video_url(item.get("video_id")),
                    "text": item.get("description", "") or item.get("title", "")
                }
                for item in fallback_items
            ]
        }

    if not context_lines and not fallback_items:
        return {
            "generated_at": generated_at,
            "battlecard": {
                "summary": "No usable transcripts found for the provided channels.",
                "concepts": [],
                "video_summaries": [],
                "new_features": [],
                "pricing_changes": [],
                "messaging_shifts": [],
                "sentiment_shift": {
                    "status": "unknown",
                    "summary": "Insufficient transcript/comment data to assess sentiment shift.",
                    "confidence": "low"
                },
                "channels": []
            },
            "evidence": []
        }

    client = get_openai_client()
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate weekly competitive battlecards from YouTube transcripts. "
                    "Extract the most important concepts discussed (from webinars, launches, "
                    "interviews). Highlight (1) new features announced, (2) pricing changes "
                    "mentioned, (3) shifts in marketing messaging, and (4) any sentiment "
                    "shift signals you can infer from tone in the transcripts. Be concise "
                    "and evidence-based. If evidence is weak, state low confidence."
                )
            },
            {
                "role": "user",
                "content": json.dumps({
                    "generated_at": generated_at,
                    "required_format": {
                        "summary": "string",
                        "concepts": ["string"],
                        "video_summaries": [
                            {
                                "video_url": "string",
                                "title": "string",
                                "summary": "string",
                                "confidence": "string"
                            }
                        ],
                        "new_features": [
                            {
                                "item": "string",
                                "channel_url": "string",
                                "video_url": "string"
                            }
                        ],
                        "pricing_changes": [
                            {
                                "item": "string",
                                "channel_url": "string",
                                "video_url": "string"
                            }
                        ],
                        "messaging_shifts": [
                            {
                                "item": "string",
                                "channel_url": "string",
                                "video_url": "string"
                            }
                        ],
                        "sentiment_shift": {
                            "status": "string",
                            "summary": "string",
                            "confidence": "string"
                        },
                        "channels": [
                            {
                                "channel_url": "string",
                                "notes": "string"
                            }
                        ]
                    },
                    "context": context,
                    "note": (
                        "If transcripts are missing, infer from titles/descriptions "
                        "and be explicit that evidence is limited."
                    )
                })
            }
        ]
    )

    battlecard = json.loads(response.choices[0].message.content)
    proof = [
        {
            "channel_url": e["channel_url"],
            "video_url": _build_video_url(e["video_id"], e.get("start")),
            "text": e["text"]
        }
        for e in all_evidence
    ]

    return {
        "generated_at": generated_at,
        "battlecard": battlecard,
        "evidence": proof
    }
