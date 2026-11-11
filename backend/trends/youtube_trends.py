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


SHORT_SECONDS = 180  # YouTube Shorts are vertical clips of up to three minutes


def _seconds(iso: str) -> int:
    import re
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m: return 0
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se


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
            q=topic + " #shorts",
            part="id",
            type="video",
            videoDuration="short",
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
        youtube.videos().list(id=",".join(video_ids), part="snippet,statistics,contentDetails").execute()
    )

    items = [i for i in videos_response.get("items", [])
             if 0 < _seconds(i.get("contentDetails", {}).get("duration", "")) <= SHORT_SECONDS]
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
                "duration": _seconds(item.get("contentDetails", {}).get("duration", "")),
                "published_at": snippet.get("publishedAt", ""),
                **{key: int(stats[api]) for key, api in (("like_count", "likeCount"), ("comment_count", "commentCount")) if str(stats.get(api, "")).isdigit()},
            }
        )
    return results

def public_search(topic,limit=5):
    """Real no-key discovery using the existing yt-dlp dependency, never invented refs.
    Looks for YouTube Shorts (short vertical clips) from the last 14 days, checks every
    candidate's real metadata at the same time, and ranks by views per hour."""
    import re
    import yt_dlp
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlencode
    from .diagnostics import StageError,stage,ydl_options
    options={**ydl_options(),'skip_download':True,'noplaylist':True,'socket_timeout':15,'retries':1}
    # sp: uploaded this week, videos under 4 minutes, sorted by view count
    url='https://www.youtube.com/results?'+urlencode({'search_query':topic+' #shorts','sp':'CAMSBAgDEAE%3D'})
    with yt_dlp.YoutubeDL({**options,'extract_flat':True,'playlistend':14}) as y:
        listing=stage('discovery',y.extract_info,url,download=False)
    candidates=[e for e in listing.get('entries',[]) if e and re.fullmatch(r'[A-Za-z0-9_-]{11}',e.get('id',''))
                and not (isinstance(e.get('duration'),(int,float)) and e['duration']>SHORT_SECONDS)]
    cutoff=datetime.fromisoformat(_recent_iso(14).replace('Z','+00:00'))
    log=logging.getLogger('cascade.trends')

    def check(entry):
        with yt_dlp.YoutubeDL(options) as y:
            info=stage('discovery_metadata',y.extract_info,'https://www.youtube.com/watch?v='+entry['id'],download=False,reference=entry['id'])
        date=info.get('upload_date')
        if not date:
            log.info('reference=%s excluded=missing_publication_date',entry['id']);return None
        published=datetime.strptime(date,'%Y%m%d').replace(tzinfo=timezone.utc)
        if published.date()<cutoff.date() or not 0<(info.get('duration') or 0)<=SHORT_SECONDS:
            log.info('reference=%s excluded=not_a_recent_short upload_day=%s duration=%s',entry['id'],date,info.get('duration'));return None
        return {'video_id':entry['id'],'title':info.get('title',''),'channel':info.get('channel') or info.get('uploader',''),
            'url':'https://www.youtube.com/watch?v='+entry['id'],'view_count':info.get('view_count') or 0,**_engagement(info),
            'published_at':published.isoformat(),'publication_precision':'day','discovery_provider':'youtube-public-search'}

    results=[];failures=[]
    with ThreadPoolExecutor(max_workers=min(8,max(1,len(candidates)))) as pool:
        for future in [pool.submit(check,e) for e in candidates]:
            try:
                found=future.result()
                if found:results.append(found)
            except Exception as exc:
                if isinstance(exc,StageError):failures.append(exc.detail)
    if not results and failures:
        from .diagnostics import ResearchFailure
        raise ResearchFailure('Public YouTube discovery found candidates but metadata could not be verified.',failures)
    results.sort(key=lambda r:_velocity({'statistics':{'viewCount':r['view_count']},'snippet':{'publishedAt':r['published_at']}}),reverse=True)
    results=results[:limit]
    if results and failures:results[0]['discovery_failures']=failures
    return results


def _engagement(info):
    """Likes, comments and length exactly as YouTube reports them (missing ones are left out)."""
    out={}
    for key in ('like_count','comment_count','duration'):
        if isinstance(info.get(key),(int,float)):out[key]=info[key]
    return out


def video_metadata(video_id: str) -> dict[str, Any]:
    """One video the user added by link: real YouTube metadata, no date window (they chose it)."""
    import re
    import yt_dlp
    from .diagnostics import ydl_options
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):raise ValueError('Not a YouTube video id.')
    with yt_dlp.YoutubeDL({**ydl_options(),'skip_download':True,'noplaylist':True}) as y:
        info=y.extract_info('https://www.youtube.com/watch?v='+video_id,download=False)
    if (info.get('duration') or 0)>600:raise RuntimeError('References longer than 10 minutes can’t be analyzed.')
    date=info.get('upload_date')
    published=datetime.strptime(date,'%Y%m%d').replace(tzinfo=timezone.utc).isoformat() if date else None
    return {'video_id':video_id,'title':info.get('title',''),'channel':info.get('channel') or info.get('uploader',''),
            'url':'https://www.youtube.com/watch?v='+video_id,'view_count':info.get('view_count') or 0,**_engagement(info),
            'published_at':published,'publication_precision':'day' if published else None,'discovery_provider':'user-link'}


def _recent_iso(days: int) -> str:
    from datetime import timedelta

    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
