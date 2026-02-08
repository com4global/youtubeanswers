from youtubesearchpython import VideosSearch


def search_videos(query: str, min_views: int = 50000, limit: int = 20):
    """
    Search YouTube videos using youtube-search-python.
    Filters by minimum view count.
    Returns list of { video_id, title }.
    """

    search = VideosSearch(query, limit=limit)
    results = []

    data = search.result()
    videos = data.get("result", [])

    for v in videos:
        try:
            # View count comes as text like "123,456 views"
            view_text = v.get("viewCount", {}).get("text", "0")
            views = int(
                view_text
                .replace(",", "")
                .replace(" views", "")
                .strip()
            )

            if views < min_views:
                continue

            results.append({
                "video_id": v.get("id"),
                "title": v.get("title"),
                "views": views
            })

        except Exception:
            # Defensive: skip malformed entries
            continue

    return results
