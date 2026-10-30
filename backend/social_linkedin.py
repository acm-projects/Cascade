"""Personal-profile LinkedIn OAuth, Videos API uploads and Posts API publication.

A saved explicit publish request is the only authority to create a post. No Page
posting, scheduling, automatic post retry, or Google credential dependency.
"""
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, quote, urlsplit, unquote, unquote_plus

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from backend import social_youtube as storage

logger = logging.getLogger(__name__)
SCOPES = {'openid', 'profile', 'w_member_social'}
ACTIVE = ('Rendering', 'Uploading', 'Processing', 'Publishing')


def cipher():
    try:
        return Fernet(os.getenv('SOCIAL_TOKEN_ENCRYPTION_KEY', '').encode())
    except (ValueError, TypeError):
        raise HTTPException(503, 'Configure SOCIAL_TOKEN_ENCRYPTION_KEY on the backend before connecting LinkedIn.')


def config():
    names = ('LINKEDIN_CLIENT_ID', 'LINKEDIN_CLIENT_SECRET', 'LINKEDIN_REDIRECT_URI')
    values = [os.getenv(name, '').strip() for name in names]
    if not all(values):
        raise HTTPException(503, 'LinkedIn is not configured. Set LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET and LINKEDIN_REDIRECT_URI, and enable Share on LinkedIn plus Sign In with LinkedIn using OpenID Connect.')
    redirect = urlsplit(values[2])
    if redirect.scheme != 'https' or not redirect.hostname or redirect.fragment or redirect.query:
        raise HTTPException(503, 'LINKEDIN_REDIRECT_URI must be the registered absolute HTTPS callback URL, without query parameters or fragment.')
    cipher()
    return values


def version():
    value = os.getenv('LINKEDIN_API_VERSION', '202607')
    if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])', value):
        raise HTTPException(503, 'LINKEDIN_API_VERSION must be a supported LinkedIn API version in YYYYMM format.')
    return value


def encrypt(data):
    return cipher().encrypt(json.dumps(data).encode()).decode()


def connection(user, expected_person=None):
    record = storage.read('linkedin_connection', user)
    if not record:
        raise HTTPException(409, 'Connect LinkedIn before publishing to your personal profile.')
    try:
        token = json.loads(cipher().decrypt(record['encrypted'].encode()))
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(409, 'LinkedIn credentials cannot be read. Reconnect LinkedIn.')
    if token['expires_at'] <= time.time()+60:
        raise HTTPException(409, 'LinkedIn authorization expired. Reconnect LinkedIn; refresh-token access is not assumed.')
    if expected_person and token['person'] != expected_person:
        raise HTTPException(409, 'The connected LinkedIn profile changed. Reconnect the original personal profile before continuing.')
    return token


def headers(token):
    return {'Authorization': 'Bearer '+token['access_token'], 'LinkedIn-Version': version(), 'X-Restli-Protocol-Version': '2.0.0'}


def checked(response, step, json_body=True):
    """Do not expose arbitrary provider text, URLs, request bodies or tokens."""
    if not response.is_success:
        status = response.status_code
        try:
            payload = response.json()
            reason = payload.get('error')
            reason = reason if reason in ('invalid_client','invalid_grant','invalid_redirect_uri','invalid_scope','unauthorized_scope_error') else 'unreported'
            code = payload.get('serviceErrorCode')
            code = str(code) if isinstance(code, int) else 'unreported'
        except (ValueError, AttributeError):
            code = reason = 'unreported'
        logger.warning('LinkedIn API failed step=%s http_status=%s service_error_code=%s reason=%s', step, status, code, reason)
        if step == 'OAuth token exchange' and reason in ('invalid_client','invalid_grant','invalid_redirect_uri'):
            hint = 'Check the LinkedIn client ID/secret and exact registered HTTPS redirect URI. Start a new connection; authorization codes are single-use.'
        elif status == 401:
            hint = 'LinkedIn authorization expired or was revoked. Reconnect LinkedIn.'
        elif status == 403:
            hint = 'Your LinkedIn developer app or member token cannot access this endpoint. Enable Share on LinkedIn (w_member_social) and verify Videos/Posts API access for the configured version. OAuth connection alone does not establish video-posting access.'
        elif status in (404, 426):
            hint = 'Check LINKEDIN_API_VERSION and whether your developer app has access to the Videos and Posts endpoints.'
        elif status == 429:
            hint = 'LinkedIn rate or quota limit reached. Wait before retrying.'
        else:
            hint = 'LinkedIn rejected this request. Check its video/content requirements and developer app access.'
        raise HTTPException(502, f'LinkedIn {step} failed (HTTP {status}, service error {code}, reason {reason}). {hint}')
    if not json_body:
        return None
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except ValueError:
        raise HTTPException(502, 'LinkedIn '+step+' returned an invalid response. No success has been confirmed.')


def upload_url(value):
    parsed = urlsplit(value)
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or not (host == 'linkedin.com' or host.endswith('.linkedin.com')) or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise HTTPException(502, 'LinkedIn returned an unexpected video upload endpoint.')
    return value


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].split('?', 1)[0] == '/api/social/linkedin/callback':
                args[2] = '/api/social/linkedin/callback';record.args = tuple(args)
        return True


class Publish(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=160)
    caption: str = Field(default='', max_length=3000)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    edit: dict
    submission_id: uuid.UUID


def commentary(body):
    if any(len(tag) > 100 or not re.fullmatch(r'#[\w]+', tag, re.UNICODE) for tag in body.hashtags):
        raise HTTPException(422, 'Use hashtags beginning with # and containing letters, numbers or underscores.')
    value = '\n\n'.join(part for part in (body.caption, ' '.join(body.hashtags)) if part)
    if len(value) > 3000:
        raise HTTPException(422, 'LinkedIn caption and hashtags together must be at most 3,000 characters.')
    # Escape caption markup; emit validated tags using LinkedIn's HashtagTemplate.
    escape = lambda text: re.sub(r'([\\|{}@\[\]()<>#*_~])', r'\\\1', text)
    tags = ' '.join('{hashtag|\\#|'+escape(tag[1:])+'}' for tag in body.hashtags)
    return '\n\n'.join(part for part in (escape(body.caption), tags) if part)


def post_body(record):
    return {'author': record['person'], 'commentary': record['commentary'], 'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'content': {'media': {'id': record['video'], 'title': record['title']}},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False}


def register(app, integration, selected, export, export_model):
    log = logging.getLogger('uvicorn.access')
    if not any(isinstance(f, CallbackLogFilter) for f in log.filters):
        log.addFilter(CallbackLogFilter())

    def key(pid, jid, index, user):
        return user+':'+pid+':'+jid+':'+str(index)

    def public(record):
        return {k: v for k, v in record.items() if k in ('status', 'error', 'url', 'post_id', 'video', 'profile', 'submission_id', 'post_attempted', 'started')}

    @app.get('/api/projects/{pid}/social/linkedin')
    def account(pid: str, request: Request):
        integration.require_project(pid, request.state.user_id)
        try:
            config();version()
        except HTTPException as exc:
            return {'configured': False, 'connected': False, 'error': exc.detail}
        try:
            token = connection(request.state.user_id)
            return {'configured': True, 'connected': True, 'profile': token['name']}
        except HTTPException as exc:
            return {'configured': True, 'connected': False, 'error': exc.detail}

    @app.post('/api/projects/{pid}/social/linkedin/connect')
    def connect(pid: str, request: Request):
        integration.require_project(pid, request.state.user_id)
        client, _, redirect = config()
        state = secrets.token_urlsafe(32)
        storage.write('linkedin_oauth', state, {'user': request.state.user_id, 'expires': time.time()+600})
        return {'url': 'https://www.linkedin.com/oauth/v2/authorization?'+urlencode({'response_type': 'code', 'client_id': client, 'redirect_uri': redirect, 'scope': ' '.join(sorted(SCOPES)), 'state': state})}

    @app.get('/api/social/linkedin/callback')
    def callback(state: str = '', code: str = '', error: str = ''):
        with storage.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT value FROM records WHERE kind='linkedin_oauth' AND key=?", (state,)).fetchone()
            c.execute("DELETE FROM records WHERE kind='linkedin_oauth' AND key=?", (state,))
        rec = json.loads(row[0]) if row else None
        if not rec or rec['expires'] < time.time():
            raise HTTPException(400, 'Invalid or expired LinkedIn connection request. Start a new connection from Cascade.')
        if error or not code:
            raise HTTPException(400, 'LinkedIn did not authorize this connection. Verify the app has openid, profile and w_member_social scopes, then connect again.')
        client, secret, redirect = config()
        try:
            response = httpx.post('https://www.linkedin.com/oauth/v2/accessToken', data={'grant_type': 'authorization_code', 'code': code, 'client_id': client, 'client_secret': secret, 'redirect_uri': redirect}, timeout=30)
            token = checked(response, 'OAuth token exchange')
            granted = set(re.split(r'[\s,]+', unquote_plus(token.get('scope', ''))))
            if not SCOPES.issubset(granted):
                raise HTTPException(409, 'LinkedIn did not grant openid, profile and w_member_social. Enable both required products in your app and reconnect.')
            profile = checked(httpx.get('https://api.linkedin.com/v2/userinfo', headers={'Authorization': 'Bearer '+token['access_token']}, timeout=30), 'profile lookup')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', profile['sub']):
                raise ValueError()
            expires = int(token['expires_in'])
            if expires <= 0:
                raise ValueError()
            data = {'access_token': token['access_token'], 'expires_at': time.time()+expires, 'person': 'urn:li:person:'+profile['sub'], 'name': str(profile.get('name') or 'LinkedIn member')[:200]}
            storage.write('linkedin_connection', rec['user'], {'encrypted': encrypt(data)})
        except httpx.RequestError:
            raise HTTPException(502, 'The backend could not reach LinkedIn during connection. Retry when network access is restored.')
        except (KeyError, ValueError, TypeError):
            raise HTTPException(502, 'LinkedIn returned incomplete token or profile information. No connection was saved.')
        return HTMLResponse('LinkedIn connected to your personal profile. Return to Cascade and click Refresh connection. Connecting does not publish a post.')

    def finish(job_key):
        with storage.schedule_lock('linkedin:'+job_key):
            record = storage.read('linkedin_publish', job_key)
            if not record or record['status'] != 'Processing' or record.get('post_attempted'):
                return public(record) if record else {'status': 'Ready'}
            try:
                token = connection(record['user'], record['person'])
                response = httpx.get('https://api.linkedin.com/rest/videos/'+quote(record['video'], safe=''), headers=headers(token), timeout=30)
                video = checked(response, 'video processing check')
                if video.get('owner') != record['person']:
                    raise HTTPException(409, 'LinkedIn video ownership could not be confirmed for the connected personal profile.')
                if video.get('status') == 'PROCESSING_FAILED':
                    raise HTTPException(409, 'LinkedIn could not process the edited MP4. Check video format, size and duration requirements; no post was created.')
                if video.get('status') == 'AVAILABLE':
                    # Durable intent prevents duplicate posts even if the provider accepts then disconnects.
                    record.update(status='Publishing', post_attempted=True)
                    storage.write('linkedin_publish', job_key, record)
                    created = httpx.post('https://api.linkedin.com/rest/posts', headers=headers(token), json=post_body(record), timeout=60)
                    checked(created, 'post creation', json_body=False)
                    post_id = unquote(created.headers.get('x-restli-id', ''))
                    if created.status_code != 201 or not re.fullmatch(r'urn:li:(?:share|ugcPost):[0-9]+', post_id):
                        raise HTTPException(502, 'LinkedIn did not return a confirmed post ID. Check your profile before retrying; duplicate submissions are blocked.')
                    record.update(status='Published', post_id=post_id, url='https://www.linkedin.com/feed/update/'+quote(post_id, safe=':')+'/')
                    record.pop('error', None)
            except (HTTPException, httpx.RequestError) as exc:
                message = exc.detail if isinstance(exc, HTTPException) else 'LinkedIn could not confirm this request. Check your connection and profile.'
                if record.get('post_attempted'):
                    message += ' The post may already exist. Check your LinkedIn profile; no automatic or duplicate retry will occur.'
                record.update(status='Failed', error=message)
            storage.write('linkedin_publish', job_key, record)
            return public(record)

    def process(job_key):
        # The saved explicit Publish request authorizes completing processing, even after the panel closes.
        for _ in range(360):
            rec = finish(job_key)
            if rec['status'] != 'Processing':
                return
            time.sleep(10)
        record = storage.read('linkedin_publish', job_key)
        if record and record['status'] == 'Processing':
            record.update(status='Failed', error='LinkedIn processing timed out. Check LinkedIn before continuing. The existing upload is retained; no duplicate post will be submitted.')
            storage.write('linkedin_publish', job_key, record)

    def run(job_key, record, edit, request):
        response = None
        try:
            connection(record['user'], record['person'])
            response = export(record['pid'], record['jid'], record['index'], edit, request)
            path = Path(response.path);size = path.stat().st_size
            if not 75000 <= size <= 500*1024*1024:
                raise HTTPException(422, 'LinkedIn video must be between 75 KB and 500 MB. Adjust the clip before retrying.')
            token = connection(record['user'], record['person']);record['status'] = 'Uploading';storage.write('linkedin_publish', job_key, record)
            with httpx.Client(timeout=120, follow_redirects=False) as client:
                initialized = checked(client.post('https://api.linkedin.com/rest/videos', params={'action':'initializeUpload'}, headers=headers(token), json={'initializeUploadRequest': {'owner':record['person'],'fileSizeBytes':size,'uploadCaptions':False,'uploadThumbnail':False}}), 'video upload initialization')['value']
                video = initialized['video']
                if not re.fullmatch(r'urn:li:video:[A-Za-z0-9_-]+', video):
                    raise ValueError()
                record['video'] = video;storage.write('linkedin_publish', job_key, record)
                parts = [];cursor = 0
                with path.open('rb') as media:
                    for instruction in initialized['uploadInstructions']:
                        first, last = instruction['firstByte'], instruction['lastByte']
                        if first != cursor or last < first or last >= size or last-first+1 > 8*1024*1024:
                            raise ValueError()
                        payload = media.read(last-first+1)
                        if len(payload) != last-first+1:
                            raise ValueError()
                        uploaded = client.put(upload_url(instruction['uploadUrl']), headers={'Authorization':'Bearer '+token['access_token'],'Content-Type':'application/octet-stream'}, content=payload)
                        checked(uploaded, 'video part upload', json_body=False)
                        part = uploaded.headers.get('etag', '').strip('"')
                        if not part:
                            raise ValueError()
                        parts.append(part);cursor=last+1
                if cursor != size:
                    raise ValueError()
                checked(client.post('https://api.linkedin.com/rest/videos', params={'action':'finalizeUpload'}, headers=headers(connection(record['user'],record['person'])), json={'finalizeUploadRequest':{'video':video,'uploadToken':initialized.get('uploadToken',''),'uploadedPartIds':parts}}), 'video upload finalization', json_body=False)
            record['status'] = 'Processing';storage.write('linkedin_publish', job_key, record)
        except Exception as exc:
            record.update(status='Failed', error=exc.detail if isinstance(exc, HTTPException) else 'LinkedIn upload could not be completed. Check network access and video requirements. No post was confirmed.')
            storage.write('linkedin_publish', job_key, record)
        finally:
            if response and response.background:
                response.background.func(*response.background.args, **response.background.kwargs)
        if record['status'] == 'Processing':
            storage.start_worker(process, (job_key,))

    @app.post('/api/projects/{pid}/editor/{jid}/{index}/publish/linkedin')
    def publish(pid: str, jid: str, index: int, body: Publish, request: Request):
        selected(pid, jid, index, request.state.user_id)
        job_key = key(pid,jid,index,request.state.user_id)
        edit = export_model.model_validate(body.edit)
        if not body.title.strip():
            raise HTTPException(422, 'Enter a title for the LinkedIn video.')
        if hasattr(edit, 'end') and not 3 <= edit.end-edit.start <= 1800:
            raise HTTPException(422, 'Choose a LinkedIn clip between 3 seconds and 30 minutes.')
        text = commentary(body)
        with storage.schedule_lock('linkedin:'+job_key):
            previous = storage.read('linkedin_publish', job_key)
            if previous and (previous['submission_id']==str(body.submission_id) or previous['status']!='Failed' or previous.get('video') or previous.get('post_attempted')):
                return public(previous)
            config();version();token = connection(request.state.user_id)
            record={'user':request.state.user_id,'pid':pid,'jid':jid,'index':index,'status':'Rendering','started':time.time(),'worker_pid':os.getpid(),'submission_id':str(body.submission_id),'person':token['person'],'profile':token['name'],'title':body.title,'commentary':text,'snapshot':body.model_dump(mode='json')}
            storage.write('linkedin_publish', job_key, record)
        storage.start_worker(run,(job_key,record,edit,request))
        return public(record)

    @app.get('/api/projects/{pid}/editor/{jid}/{index}/publish/linkedin')
    def status(pid: str, jid: str, index: int, request: Request):
        selected(pid,jid,index,request.state.user_id)
        job_key=key(pid,jid,index,request.state.user_id)
        record=storage.read('linkedin_publish',job_key)
        if not record:
            return {'status':'Ready'}
        # GET is read-only: a new browser request can never create a LinkedIn post.
        if record['status'] in ACTIVE:
            try:
                os.kill(record['worker_pid'],0)
            except ProcessLookupError:
                record.update(status='Failed',error='LinkedIn publishing was interrupted. Check your profile before retrying. The saved upload is retained; duplicate submissions are blocked.')
                storage.write('linkedin_publish',job_key,record)
        return public(record)
