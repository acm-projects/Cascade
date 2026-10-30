"""Fetch trending videos for a topic via the YouTube Data API v3."""

from __future__ import annotations

import os
import logging
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
    key = os.environ.get('YOUTUBE_API_KEY') or YOUTUBE_API_KEY
    if not key:
        logging.getLogger('cascade.trends').warning('YOUTUBE_API_KEY absent; using real public YouTube search with verified upload dates.')
        return public_search(topic,limit)

    youtube = build("youtube", "v3", developerKey=key, cache_discovery=False)

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

def public_search(topic,limit=5):
    """Real no-key discovery using the existing yt-dlp dependency, never invented refs.
    Fetch actual per-video metadata to enforce the same 14-day window. Public search
    can be blocked independently of Data API access; failures stay visible.
    """
    import yt_dlp
    from urllib.parse import urlencode
    from .diagnostics import stage,ydl_options
    options={**ydl_options(),'skip_download':True,'noplaylist':True}
    url='https://www.youtube.com/results?'+urlencode({'search_query':topic,'sp':'CAISBAgEEAE='})
    with yt_dlp.YoutubeDL({**options,'extract_flat':True,'playlistend':10}) as y:
        listing=stage('discovery',y.extract_info,url,download=False)
    results=[];failures=[]
    cutoff=datetime.fromisoformat(_recent_iso(14).replace('Z','+00:00'))
    with yt_dlp.YoutubeDL(options) as y:
        for entry in listing.get('entries',[]):
            import re
            if not entry or not re.fullmatch(r'[A-Za-z0-9_-]{11}',entry.get('id','')):continue
            try:
                info=stage('discovery_metadata',y.extract_info,'https://www.youtube.com/watch?v='+entry['id'],download=False,reference=entry['id'])
                date=info.get('upload_date')
                if not date:
                    logging.getLogger('cascade.trends').info('reference=%s excluded=missing_publication_date',entry['id']);continue
                published=datetime.strptime(date,'%Y%m%d').replace(tzinfo=timezone.utc)
                if published.date()<cutoff.date() or (info.get('duration') or 0)>600:
                    logging.getLogger('cascade.trends').info('reference=%s excluded=outside_date_or_duration_window upload_day=%s duration=%s',entry['id'],date,info.get('duration'));continue
                results.append({'video_id':entry['id'],'title':info.get('title',''),'channel':info.get('channel') or info.get('uploader',''),
                    'url':'https://www.youtube.com/watch?v='+entry['id'],'view_count':info.get('view_count') or 0,
                    'published_at':published.isoformat(),'publication_precision':'day','discovery_provider':'youtube-public-search'})
                if len(results)>=limit:break
            except Exception as exc:
                from .diagnostics import StageError
                if isinstance(exc,StageError):failures.append(exc.detail)
    if not results and failures:
        from .diagnostics import ResearchFailure
        raise ResearchFailure('Public YouTube discovery found candidates but metadata could not be verified.',failures)
    results.sort(key=lambda r:_velocity({'statistics':{'viewCount':r['view_count']},'snippet':{'publishedAt':r['published_at']}}),reverse=True)
    if results and failures:results[0]['discovery_failures']=failures
    return results


def _recent_iso(days: int) -> str:
    from datetime import timedelta

    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
