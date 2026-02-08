from urllib.parse import urlparse, parse_qs
from youtubesearchpython import Playlist, Video


def _extract_video_id_from_link(link: str) -> str | None:
    try:
        parsed = urlparse(link)
        query = parse_qs(parsed.query)
        video_ids = query.get("v", [])
        if video_ids:
            return video_ids[0]
    except Exception:
        return None
    return None


def _extract_playlist_id(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        list_ids = query.get("list", [])
        if list_ids:
            return list_ids[0]
    except Exception:
        return None
    return None


def fetch_playlist_videos(playlist_url: str, limit: int = 200) -> list[dict]:
    """
    Fetch videos from a YouTube playlist URL (or a single watch URL).
    Returns list of { video_id, title }.
    """
    playlist_id = _extract_playlist_id(playlist_url)
    if not playlist_id:
        video_id = _extract_video_id_from_link(playlist_url)
        if not video_id:
            raise ValueError(
                "Invalid playlist URL. It must include a list= parameter "
                "(e.g. https://www.youtube.com/playlist?list=... or watch?v=...&list=...) "
                "or a single video URL with v=."
            )

        title = ""
        link = f"https://www.youtube.com/watch?v={video_id}"
        try:
            info = Video.getInfo(link, mode=Video.MODE_DICT)
            title = info.get("title") or ""
        except Exception:
            title = ""

        return [{
            "video_id": video_id,
            "title": title,
            "link": link,
            "duration": ""
        }]

    normalized_url = f"https://www.youtube.com/playlist?list={playlist_id}"

    try:
        playlist = Playlist(normalized_url)
        videos = playlist.videos or []
    except Exception as e:
        raise ValueError(f"Failed to load playlist. {e}")

    results = []
    for v in videos[:limit]:
        video_id = v.get("id")
        if not video_id:
            video_id = _extract_video_id_from_link(v.get("link", ""))
        if not video_id:
            continue

        results.append({
            "video_id": video_id,
            "title": v.get("title") or "",
            "link": v.get("link") or "",
            "duration": v.get("duration") or ""
        })

    return results
