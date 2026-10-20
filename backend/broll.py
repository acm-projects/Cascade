"""Clip-scoped Pexels registry. Browser/AI references never become fetch URLs."""
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

LOCK = threading.RLock()
MAX_BYTES = 100 * 1024 * 1024
CACHE_BYTES = 1024 * 1024 * 1024
TTL = 24 * 60 * 60


class Asset(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(pattern=r'^px-[0-9]+-[0-9]+$')
    provider_id: int = Field(gt=0)
    creator: str = Field(max_length=300)
    creator_url: str = Field(max_length=1000)
    source_url: str = Field(max_length=1000)
    duration: float = Field(gt=0, le=86400)
    width: int = Field(gt=0, le=4096)
    height: int = Field(gt=0, le=4096)


class Segment(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    asset: Asset
    start: float = Field(ge=0)
    duration: float = Field(ge=.05)
    offset: float = Field(default=0, ge=0)
    mode: Literal['fit', 'fill'] = 'fill'


def validate_segments(segments, duration):
    if len(segments)>30:
        raise HTTPException(422, 'Use at most 30 B-roll segments per clip.')
    seen = set()
    previous_end = 0
    for s in sorted(segments, key=lambda x: x.start):
        if s.id in seen:
            raise HTTPException(422, 'B-roll segment IDs must be unique.')
        seen.add(s.id)
        if s.start+s.duration > duration+1e-6 or s.offset+s.duration > s.asset.duration+1e-6:
            raise HTTPException(422, 'B-roll must fit inside the generated clip and available stock footage. Reduce duration or source offset.')
        if s.start < previous_end-1e-6:
            raise HTTPException(422, 'B-roll segments cannot overlap. Move or shorten a segment first.')
        previous_end = s.start+s.duration


def provider_url(url, kind):
    """Only exact HTTPS provider hosts, no redirects, credentials, ports or queries."""
    try:
        p = urlsplit(url)
        hosts = {'video': {'videos.pexels.com'}, 'image': {'images.pexels.com'},
                 'page': {'www.pexels.com', 'pexels.com'}}[kind]
        if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443) or p.fragment:
            raise ValueError()
        if kind == 'video' and (p.query or not p.path.lower().endswith('.mp4')):
            raise ValueError()
        return url
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(502, 'Pexels returned an unsupported media address.')


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        json.dump(data, stream)
    tmp.replace(path)


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)

    def registry(self):
        path = self.folder/'assets.json'
        return json.loads(path.read_text()) if path.is_file() else {}

    def entry(self, asset_id):
        if not re.fullmatch(r'px-[0-9]+-[0-9]+', asset_id):
            raise HTTPException(422, 'Invalid B-roll asset reference.')
        item = self.registry().get(asset_id)
        if item is None:
            raise HTTPException(422, 'B-roll asset is not known for this clip. Search and select footage first.')
        return item

    def verify(self, state):
        for segment in state.broll:
            if segment.asset.model_dump() != self.entry(segment.asset.id)['asset']:
                raise HTTPException(422, 'B-roll metadata does not match the selected provider asset.')

    def search(self, query, page=1):
        query = query.strip()
        if not 1 <= len(query) <= 160 or not 1 <= page <= 100 or any(ord(c)<32 for c in query):
            raise HTTPException(422, 'Enter a search of 1–160 characters and a page from 1–100.')
        key = os.getenv('PEXELS_API_KEY', '').strip()
        if not key:
            raise HTTPException(503, 'Pexels is not configured. Set PEXELS_API_KEY in the backend .env and restart the server.')
        cache_key = hashlib.sha256(json.dumps([query.casefold(), page]).encode()).hexdigest()
        path = self.folder/'search'/f'{cache_key}.json'
        with LOCK:
            if path.is_file() and time.time()-path.stat().st_mtime < TTL:
                return json.loads(path.read_text())
            try:
                response = httpx.get('https://api.pexels.com/v1/videos/search',
                                     params={'query': query, 'page': page, 'per_page': 12},
                                     headers={'Authorization': key}, timeout=httpx.Timeout(20, connect=5), follow_redirects=False)
                if response.status_code == 429:
                    raise HTTPException(429, 'Pexels request limit reached. Try again later; cached searches remain available.')
                if response.status_code in (401, 403):
                    raise HTTPException(503, 'Pexels authentication failed. Check the server API key and restart.')
                if response.status_code != 200:
                    raise HTTPException(502, 'Pexels search is unavailable. Retry shortly.')
                data = response.json()
                if not isinstance(data,dict) or not isinstance(data.get('videos'),list):
                    raise ValueError('Invalid provider response')
                registry = self.registry()
                results = []
                for video in data['videos'][:12]:
                    if not isinstance(video,dict): continue
                    try:
                        files = [f for f in video.get('video_files', []) if f.get('file_type') == 'video/mp4'
                                 and 0 < int(f.get('width') or 0) <= 1920 and 0 < int(f.get('height') or 0) <= 1920]
                        if not files:
                            continue
                        rendition = min(files, key=lambda f: abs(max(f['width'], f['height'])-1280))
                        asset = Asset(id=f"px-{int(video['id'])}-{int(rendition['id'])}", provider_id=int(video['id']),
                                      creator=str(video['user']['name']), creator_url=provider_url(video['user']['url'], 'page'),
                                      source_url=provider_url(video['url'], 'page'), duration=video['duration'],
                                      width=rendition['width'], height=rendition['height']).model_dump()
                        # Keep verified metadata stable for already-saved drafts.
                        registry.setdefault(asset['id'], {'asset': asset, 'video': provider_url(rendition['link'], 'video'),
                                                          'image': provider_url(video['image'], 'image')})
                        results.append(registry[asset['id']]['asset'])
                    except (KeyError, ValueError, TypeError, HTTPException):
                        continue
                if len(registry) > 2000:
                    raise HTTPException(409, 'This clip has reached its stock search limit. Use an existing result.')
                write_json(self.folder/'assets.json', registry)
                result = {'results': results, 'page': page, 'query': query,
                          'has_more': bool(data.get('next_page')) and page < 100}
                write_json(path, result)
                for old in sorted(path.parent.glob('*.json'), key=lambda p:p.stat().st_mtime)[:-100]:
                    old.unlink(missing_ok=True)
                return result
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                # Never echo provider bodies, exception strings, headers, or request objects.
                raise HTTPException(502, 'Could not reach Pexels or read its response. Retry shortly.')

    def media(self, asset_id, image=False):
        with LOCK:
            entry = self.entry(asset_id)
            kind = 'image' if image else 'video'
            target = self.folder/(asset_id+('.jpg' if image else '.mp4'))
            if target.is_file():
                return target
            self.folder.mkdir(parents=True, exist_ok=True)
            used_bytes=sum(p.stat().st_size for p in self.folder.glob('*') if p.is_file())
            if used_bytes >= CACHE_BYTES:
                raise HTTPException(409, 'This clip’s stock cache is full. Existing downloaded footage remains available.')
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.folder, delete=False) as output:
                    tmp = Path(output.name)
                    # No API credentials are sent to media hosts. Redirects are deliberately rejected.
                    with httpx.stream('GET', provider_url(entry[kind], kind), timeout=httpx.Timeout(30, connect=5), follow_redirects=False) as response:
                        if response.status_code != 200:
                            raise HTTPException(502, 'Stock footage download failed. Try another result.')
                        maximum = 5*1024*1024 if image else MAX_BYTES
                        total = 0
                        deadline = time.monotonic()+90
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > maximum or used_bytes+total > CACHE_BYTES or time.monotonic() > deadline:
                                raise HTTPException(422, 'Stock media is too large or too slow. Choose another result.')
                            output.write(chunk)
                if image:
                    from PIL import Image
                    with Image.open(tmp) as source:
                        if source.width > 8192 or source.height > 8192:
                            raise ValueError()
                        source.verify()
                else:
                    info = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', 'mov', '-show_entries', 'format=duration:stream=codec_type,width,height',
                                                      '-of', 'json', str(tmp)], capture_output=True, text=True, check=True, timeout=20).stdout)
                    stream = next(s for s in info['streams'] if s.get('codec_type') == 'video')
                    duration = float(info['format']['duration'])
                    if not math.isfinite(duration) or duration+.05 < entry['asset']['duration'] or duration > 86400 or not 0 < stream['width'] <= 4096 or not 0 < stream['height'] <= 4096:
                        raise ValueError()
                tmp.replace(target)
                return target
            except (httpx.HTTPError, OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
                raise HTTPException(502, 'Stock media could not be downloaded or validated. Choose another result.')
            finally:
                if tmp:
                    tmp.unlink(missing_ok=True)
