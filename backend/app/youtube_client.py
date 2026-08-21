"""
Thin wrapper around the YouTube Data API v3 - search only, read-only. Uses
a plain API key (like Tavily web search), not OAuth: searching YouTube's
public catalog isn't "acting as" anyone, so there's no personal account to
connect here, unlike Gmail/Drive/Calendar.

Enriches search results with view counts via a second call - a nice-to-have
for the actual use case this exists for (spotting what's already been
covered on a topic, and how well it did, before proposing new video ideas),
so a failure fetching stats doesn't fail the whole search.
"""
import httpx

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeError(Exception):
    pass


def search_videos(api_key: str, query: str, max_results: int = 10) -> list[dict]:
    try:
        resp = httpx.get(
            SEARCH_URL,
            params={
                "part": "snippet", "q": query, "type": "video",
                "maxResults": max_results, "key": api_key, "order": "relevance",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            raise YouTubeError(
                "The YouTube API key on the Settings page looks invalid, or today's free quota is used up"
            ) from exc
        raise YouTubeError(f"YouTube search failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise YouTubeError(f"Couldn't reach YouTube: {exc}") from exc

    items = resp.json().get("items", [])
    video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]
    stats_by_id = _fetch_stats(api_key, video_ids) if video_ids else {}

    results = []
    for item in items:
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})
        stats = stats_by_id.get(video_id, {})
        results.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt", ""),
            "view_count": stats.get("viewCount"),
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        })
    return results


def _fetch_stats(api_key: str, video_ids: list[str]) -> dict:
    try:
        resp = httpx.get(
            VIDEOS_URL, params={"part": "statistics", "id": ",".join(video_ids), "key": api_key}, timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return {}  # stats are a nice-to-have - don't fail the whole search over them
    return {item["id"]: item.get("statistics", {}) for item in resp.json().get("items", [])}
