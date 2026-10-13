"""Fetch trending videos for a topic via the YouTube Data API v3."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")


def _velocity(item: dict[str, Any]) -> float:
    """Rough proxy for "trending": views per hour since publish."""
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})

    view_count = int(stats.get("viewCount", 0))
    published_at = snippet.get("publishedAt")
    if not published_at:
        return 0.0

    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    hours = max((datetime.now(timezone.utc) - published).total_seconds() / 3600, 1.0)
    return view_count / hours


def get_trending_videos(topic: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search YouTube for a topic and return the top videos by view velocity.

    Returns a list of dicts: {video_id, title, channel, url, view_count, published_at}
    """
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is not set")

    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    search_response = (
        youtube.search()
        .list(
            q=topic,
            part="id",
            type="video",
            order="viewCount",
            maxResults=25,
            publishedAfter=_recent_iso(days=14),
        )
        .execute()
    )

    video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
    if not video_ids:
        return []

    videos_response = (
        youtube.videos().list(id=",".join(video_ids), part="snippet,statistics").execute()
    )

    items = videos_response.get("items", [])
    items.sort(key=_velocity, reverse=True)

    results = []
    for item in items[:limit]:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        video_id = item["id"]
        results.append(
            {
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "view_count": int(stats.get("viewCount", 0)),
                "published_at": snippet.get("publishedAt", ""),
            }
        )
    return results


def _recent_iso(days: int) -> str:
    from datetime import timedelta

    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
