"""Provider adapters. No automatic retry of a possibly accepted post creation."""
import re
from pathlib import Path
from urllib.parse import quote, unquote
import httpx
from fastapi import HTTPException
from backend import social_youtube as yt, social_linkedin as li
from backend import youtube_schedule as times
from backend import publishing_store as store


class Temporary(Exception):
    pass


class ActionRequired(Exception):
    pass


def checked(response, step):
    if response.status_code == 429 or response.status_code >= 500:
        raise Temporary(f'{step}: provider temporarily unavailable (HTTP {response.status_code}).')
    if not response.is_success:
        raise ActionRequired(f'{step}: HTTP {response.status_code}. Renew the original account connection or check provider permissions, quota and video requirements.')
    return response


def account(platform, user):
    if platform == 'youtube':
        rec = yt.read('connection', user) or {}
        if not rec.get('channel_id'):
            raise HTTPException(409, 'Connect YouTube and grant video management permission first.')
        yt.connection_for({'user':user, 'channel_id':rec['channel_id']}, manage=True)
        return rec['channel_id'], rec['channel']
    li.config();li.version()
    token = li.connection(user)
    return token['person'], token['name']


def token(record):
    if record['platform'] == 'youtube':
        return yt.connection_for({**record, 'channel_id':record['account_id']}, manage=True)
    return li.connection(record['user'], record['account_id'])


class Providers:
    def prepare(self, r):
        return self.youtube(r) if r['platform'] == 'youtube' else self.linkedin_prepare(r)

    def youtube(self, r):
        access = token(r)
        headers = {'Authorization':'Bearer '+access}
        if not r.get('provider_id'):
            if r.get('phase') == 'upload_intent':
                raise ActionRequired('An interrupted upload may exist privately in YouTube Studio. No duplicate upload will be attempted. Review Studio; this job has not been confirmed scheduled.')
            # Initializing a session does not publish media. The session URL is
            # deliberately never returned or logged. Private upload first.
            path = Path(r['media_path'])
            start = checked(httpx.post('https://www.googleapis.com/upload/youtube/v3/videos', params={'uploadType':'resumable','part':'snippet,status'}, headers={**headers,'X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(path.stat().st_size)}, json={'snippet':{'title':r['title'],'description':r['description']},'status':{'privacyStatus':'private','selfDeclaredMadeForKids':r['snapshot']['settings']['made_for_kids']}}, timeout=60), 'YouTube upload initialization')
            location = start.headers.get('location','')
            if not location.startswith('https://www.googleapis.com/'):
                raise ActionRequired('YouTube returned an unexpected upload endpoint.')
            store.save(r, phase='upload_intent')
            with path.open('rb') as media:
                response = httpx.put(location, headers={**headers,'Content-Type':'video/mp4','Content-Length':str(path.stat().st_size)}, content=media, timeout=180)
            # Once bytes are sent an unknown outcome MUST NOT trigger reupload.
            checked(response, 'YouTube upload')
            video_id = response.json().get('id','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',video_id):
                raise ActionRequired('YouTube did not confirm an upload ID. Check Studio; no new upload will be attempted.')
            store.save(r, provider_id=video_id, phase='processing', url='https://www.youtube.com/watch?v='+video_id)
        item = self.youtube_item(r)
        status = item.get('status',{})
        if status.get('privacyStatus') == 'public':
            return 'Published'
        processing = item.get('processingDetails',{}).get('processingStatus')
        if processing in ('failed','terminated') or status.get('uploadStatus') in ('failed','rejected','deleted'):
            raise ActionRequired('YouTube rejected the video. Review YouTube Studio; the upload is retained.')
        if r.get('phase') == 'armed':
            if not times.matches(status,r['schedule']['publish_at']):
                raise ActionRequired('YouTube schedule was changed or removed externally. Review YouTube Studio.')
            return 'Scheduled'
        if processing != 'succeeded':
            return 'Preparing'
        if r.get('cover_path') and not r.get('cover_uploaded'):
            with open(r['cover_path'],'rb') as cover:
                checked(httpx.post('https://www.googleapis.com/upload/youtube/v3/thumbnails/set', params={'videoId':r['provider_id']}, headers={**headers,'Content-Type':'image/jpeg'}, content=cover, timeout=60), 'YouTube cover upload')
            store.save(r, cover_uploaded=True)
        self.change_native(r, r['schedule'])
        store.save(r, phase='armed')
        return 'Scheduled'

    def youtube_item(self, r):
        response = checked(httpx.get('https://www.googleapis.com/youtube/v3/videos', params={'part':'status,processingDetails,snippet','id':r['provider_id']}, headers={'Authorization':'Bearer '+token(r)}, timeout=30), 'YouTube lookup')
        items = response.json().get('items',[])
        if not items or items[0].get('snippet',{}).get('channelId') != r['account_id']:
            raise ActionRequired('YouTube upload missing or owned by a different channel. Reconnect the original account.')
        return items[0]

    def change_native(self, r, schedule):
        item = self.youtube_item(r)
        status = item.get('status',{})
        if status.get('privacyStatus') != 'private':
            raise ActionRequired('This YouTube video is no longer private. No schedule mutation was made. Review Studio immediately.')
        target = schedule['publish_at'] if schedule else None
        if times.matches(status,target):
            return
        if schedule:
            times.validate_lead(schedule)
        response = httpx.put('https://www.googleapis.com/youtube/v3/videos', params={'part':'status'}, headers={'Authorization':'Bearer '+token(r)}, json={'id':r['provider_id'],'status':times.status_payload(status,target)}, timeout=30)
        checked(response,'YouTube schedule update')
        if not times.matches(self.youtube_item(r).get('status',{}),target):
            raise ActionRequired('YouTube has not confirmed this schedule change. Check Studio; the saved change intent will be reconciled without reuploading.')

    def linkedin_prepare(self, r):
        auth = token(r);headers = li.headers(auth)
        if not r.get('provider_id'):
            if r.get('phase') == 'upload_intent':
                raise ActionRequired('LinkedIn upload was interrupted. No public post was requested. Review the connection before scheduling a new submission.')
            path = Path(r['media_path']);size = path.stat().st_size
            if not 75000 <= size <= 500*1024*1024 or not 3 <= r['media_duration'] <= 1800:
                raise ActionRequired('LinkedIn requires MP4, 3 seconds–30 minutes and 75 KB–500 MB. Adjust the clip.')
            init = checked(httpx.post('https://api.linkedin.com/rest/videos', params={'action':'initializeUpload'}, headers=headers, json={'initializeUploadRequest':{'owner':r['account_id'],'fileSizeBytes':size,'uploadCaptions':False,'uploadThumbnail':bool(r.get('cover_path'))}}, timeout=60), 'LinkedIn upload initialization').json()['value']
            video = init['video']
            if not re.fullmatch(r'urn:li:video:[A-Za-z0-9_-]+',video):
                raise ActionRequired('LinkedIn returned an invalid video ID.')
            store.save(r, phase='upload_intent')
            parts = [];cursor = 0
            with path.open('rb') as media:
                for instruction in init['uploadInstructions']:
                    first,last = instruction['firstByte'],instruction['lastByte']
                    if first != cursor or last < first or last >= size or last-first+1 > 8*1024*1024:
                        raise ActionRequired('LinkedIn returned invalid upload byte ranges.')
                    payload = media.read(last-first+1)
                    uploaded = checked(httpx.put(li.upload_url(instruction['uploadUrl']), headers={'Authorization':headers['Authorization'],'Content-Type':'application/octet-stream'}, content=payload, timeout=120), 'LinkedIn media upload')
                    part = uploaded.headers.get('etag','').strip('"')
                    if not part: raise ActionRequired('LinkedIn did not acknowledge a video part.')
                    parts.append(part);cursor=last+1
            if cursor != size: raise ActionRequired('LinkedIn upload was incomplete.')
            if r.get('cover_path'):
                with open(r['cover_path'],'rb') as cover:
                    checked(httpx.put(li.upload_url(init['thumbnailUploadUrl']), headers={'Authorization':headers['Authorization'],'Content-Type':'image/jpeg'}, content=cover, timeout=60),'LinkedIn cover upload')
            checked(httpx.post('https://api.linkedin.com/rest/videos', params={'action':'finalizeUpload'}, headers=headers, json={'finalizeUploadRequest':{'video':video,'uploadToken':init.get('uploadToken',''),'uploadedPartIds':parts}}, timeout=60),'LinkedIn upload finalization')
            store.save(r, provider_id=video, phase='processing')
        response = checked(httpx.get('https://api.linkedin.com/rest/videos/'+quote(r['provider_id'],safe=''), headers=headers, timeout=30),'LinkedIn processing lookup').json()
        if response.get('owner') != r['account_id']:
            raise ActionRequired('LinkedIn video account ownership could not be confirmed.')
        if response.get('status') == 'PROCESSING_FAILED': raise ActionRequired('LinkedIn video processing failed. Check video requirements.')
        return 'Scheduled' if response.get('status') == 'AVAILABLE' else 'Preparing'

    def publish_linkedin(self, r):
        auth = token(r)  # Preflight auth before persisting uncertain send intent.
        if r.get('phase') == 'post_intent':
            if r.get('post_id'):
                response = checked(httpx.get('https://api.linkedin.com/rest/posts/'+quote(r['post_id'],safe=''),headers=li.headers(auth),timeout=30),'LinkedIn post reconciliation')
                if response.json().get('lifecycleState') == 'PUBLISHED': return 'Published'
            raise ActionRequired('LinkedIn may have accepted the post before the worker stopped. Check the original profile. No automatic retry: member post lookup/search may require restricted r_member_social permission.')
        body = li.post_body({'person':r['account_id'],'commentary':r['linkedin_commentary'],'video':r['provider_id'],'title':r['title']})
        store.save(r, phase='post_intent')
        response = httpx.post('https://api.linkedin.com/rest/posts', headers=li.headers(auth), json=body, timeout=60)
        if response.status_code == 429:
            # Explicit quota rejection confirms no post was created.
            store.save(r, phase='ready')
            raise Temporary('LinkedIn quota limit. Publication will retry within the overdue window.')
        checked(response,'LinkedIn post creation')
        post_id = unquote(response.headers.get('x-restli-id',''))
        if response.status_code != 201 or not re.fullmatch(r'urn:li:(share|ugcPost):[0-9]+',post_id):
            raise ActionRequired('LinkedIn returned no confirmed post ID. Check the profile before any new submission.')
        store.save(r, post_id=post_id, url='https://www.linkedin.com/feed/update/'+quote(post_id,safe=':')+'/')
        return 'Published'
