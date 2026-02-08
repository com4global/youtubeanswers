from urllib.parse import urlparse, parse_qs
from youtubesearchpython import ChannelSearch, ChannelsSearch, VideosSearch, Channel, Video
from youtubesearchpython.core.constants import ChannelRequestType


def _extract_channel_id_from_url(channel_url: str) -> str | None:
    try:
        parsed = urlparse(channel_url)
        parts = [p for p in parsed.path.split("/") if p]
        if "channel" in parts:
            idx = parts.index("channel")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except Exception:
        return None
    return None


def _extract_video_id_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        if parsed.netloc in {"youtu.be", "www.youtu.be"}:
            vid = parsed.path.lstrip("/")
            return vid or None
        query = parse_qs(parsed.query)
        video_ids = query.get("v", [])
        if video_ids:
            return video_ids[0]
    except Exception:
        return None
    return None


def extract_video_id(url: str) -> str | None:
    return _extract_video_id_from_url(url)


def resolve_channel_id(channel_url: str) -> str | None:
    channel_id = _extract_channel_id_from_url(channel_url)
    if channel_id:
        return channel_id

    try:
        video_id = _extract_video_id_from_url(channel_url)
        if video_id:
            info = _safe_video_info(f"https://www.youtube.com/watch?v={video_id}")
            if isinstance(info, dict):
                channel = info.get("channel", {}) if isinstance(info.get("channel"), dict) else {}
                return (
                    channel.get("id")
                    or channel.get("channelId")
                    or info.get("channelId")
                )

        parsed = urlparse(channel_url)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return None

        handle = parts[-1].lstrip("@")
        if not handle:
            return None

        search = ChannelsSearch(handle, limit=1)
        data = _safe_search_result(search)
        if data:
            return data[0].get("id")
    except Exception:
        return None

    return None


def get_channel_title(channel_id: str) -> str | None:
    try:
        info = Channel.get(channel_id, ChannelRequestType.info)
        return info.get("title")
    except Exception:
        return None


def _safe_search_result(search) -> list[dict]:
    try:
        return search.result().get("result", [])
    except Exception:
        return []


def _safe_video_info(link: str) -> dict:
    try:
        return Video.getInfo(link, mode=Video.MODE_DICT)
    except Exception:
        return {}


def get_video_info(link: str) -> dict:
    return _safe_video_info(link)


def search_channel_videos(channel_id: str, query: str, limit: int = 5) -> list[dict]:
    try:
        search = ChannelSearch(query, channel_id)
        data = _safe_search_result(search)
    except Exception:
        return []

    results = []
    for v in data[:limit]:
        video_id = v.get("id")
        if not video_id:
            continue
        description_snippet = v.get("descriptionSnippet") or ""
        if isinstance(description_snippet, list):
            description_snippet = " ".join(
                d.get("text", "") for d in description_snippet if isinstance(d, dict)
            )
        published = v.get("published") or ""
        results.append({
            "video_id": video_id,
            "title": v.get("title") or "",
            "link": f"https://youtube.com/watch?v={video_id}"
            ,
            "description": description_snippet,
            "published": published
        })

    return results


def search_channel_videos_fallback(channel_id: str, channel_title: str | None, limit: int = 6) -> list[dict]:
    queries = [
        "announcement",
        "new feature",
        "pricing",
        "update",
        "launch"
    ]
    if channel_title:
        queries = [f"{channel_title} {q}" for q in queries]

    seen = set()
    results = []
    for q in queries:
        try:
            search = VideosSearch(q, limit=limit)
            data = _safe_search_result(search)
        except Exception:
            continue
        for v in data:
            channel = v.get("channel", {})
            if channel.get("id") != channel_id:
                continue
            vid = v.get("id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            description_snippet = v.get("descriptionSnippet") or ""
            if isinstance(description_snippet, list):
                description_snippet = " ".join(
                    d.get("text", "") for d in description_snippet if isinstance(d, dict)
                )
            results.append({
                "video_id": vid,
                "title": v.get("title") or "",
                "link": v.get("link") or f"https://youtube.com/watch?v={vid}",
                "description": description_snippet,
                "published": v.get("publishedTime") or ""
            })
            if len(results) >= limit:
                return results

    return results
