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


# ---------- English only ----------
# Common words that tell English apart from the other languages trending Shorts most often come in.
_ENGLISH = set("the and you your this that what with for are was is it to of in on my me how why when just do can be "
               "have so they we i he she his her our not but all if get got when who will would this from about".split())
_OTHER = set("el la los las que del y en es por para una un con lo se su al más pero como esta este eso muy "
             "também não uma você com mais isso é le les des et est pour pas une dans qui ce avec sur "
             "yang dan ini itu di ke dari untuk tidak aku kamu und ist nicht ich mit auf ein eine zu von "
             "il che sono non è per ma ki hai nahi kya".split())


def looks_english(*texts, language=None):
    """True when a video seems to be English: the language YouTube reports for it (when it reports one), the script
    of its title/description, and whether its words are common English ones rather than another language's."""
    if language and not str(language).lower().startswith("en"):
        return False
    text = " ".join(t for t in texts if t)
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isascii() for c in letters) / len(letters) < 0.9:
        return False   # mostly another script: Devanagari, Arabic, Cyrillic, Chinese, Korean, …
    words = __import__("re").findall(r"[a-zà-ÿ']+", text.lower())
    return sum(w in _OTHER for w in words) <= sum(w in _ENGLISH for w in words)


def says_something(title):
    """False for titles that are only hashtags/emoji (#viral #reels #shorts …): those are almost never relevant."""
    import re
    return len(re.findall(r"[A-Za-z']{2,}", re.sub(r"#\w+", " ", title or ""))) >= 2


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
            relevanceLanguage="en",   # English videos only (checked again below)
            regionCode="US",
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
             if 0 < _seconds(i.get("contentDetails", {}).get("duration", "")) <= SHORT_SECONDS
             and says_something(i.get("snippet", {}).get("title", ""))
             and looks_english(i.get("snippet", {}).get("title", ""), i.get("snippet", {}).get("description", "")[:300],
                               language=i.get("snippet", {}).get("defaultAudioLanguage") or i.get("snippet", {}).get("defaultLanguage"))]
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
                "tags": snippet.get("tags", [])[:15],
                "description": snippet.get("description", "")[:300],
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
    options={**ydl_options(),'skip_download':True,'noplaylist':True,'socket_timeout':15,'retries':1,
             'http_headers':{**ydl_options().get('http_headers',{}),'Accept-Language':'en-US,en;q=0.9'}}
    # sp: uploaded this week, videos under 4 minutes, sorted by view count
    # hl/gl: ask for the English, US version of the results (each video's language is checked again below)
    url='https://www.youtube.com/results?'+urlencode({'search_query':topic+' #shorts','sp':'CAMSBAgDEAE%3D','hl':'en','gl':'US'})
    with yt_dlp.YoutubeDL({**options,'extract_flat':True,'playlistend':20}) as y:
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
        if not says_something(info.get('title','')):
            log.info('reference=%s excluded=hashtag_only_title',entry['id']);return None
        if not looks_english(info.get('title',''),(info.get('description') or '')[:300],language=info.get('language')):
            log.info('reference=%s excluded=not_english language=%s',entry['id'],info.get('language'));return None
        return {'video_id':entry['id'],'title':info.get('title',''),'channel':info.get('channel') or info.get('uploader',''),
            'url':'https://www.youtube.com/watch?v='+entry['id'],'view_count':info.get('view_count') or 0,**_engagement(info),
            'published_at':published.isoformat(),'publication_precision':'day','discovery_provider':'youtube-public-search',
            'tags':(info.get('tags') or [])[:15],'description':(info.get('description') or '')[:300]}

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
