"""Backend-only OAuth and durable, owner-scoped YouTube publishing records."""
import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
import uuid
if os.name == "nt":
    import msvcrt
else:
    import fcntl
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Literal
from backend import youtube_schedule as scheduling

logger = logging.getLogger(__name__)
# Only known provider identifiers may reach logs; never log raw responses or exceptions.
SAFE_REASONS = {
    'invalid_grant', 'invalid_client', 'redirect_uri_mismatch', 'access_denied',
    'invalid_request', 'unauthorized_client', 'invalid_scope', 'accessNotConfigured',
    'SERVICE_DISABLED', 'API_DISABLED', 'PERMISSION_DENIED', 'ACCESS_TOKEN_SCOPE_INSUFFICIENT',
    'insufficientPermissions', 'forbidden', 'youtubeSignupRequired', 'quotaExceeded',
    'dailyLimitExceeded', 'rateLimitExceeded', 'authError', 'UNAUTHENTICATED',
    'accountDelegationForbidden', 'channelNotFound', 'invalidPublishAt', 'invalidVideoMetadata',
    'uploadLimitExceeded', 'forbiddenPrivacySetting', 'videoNotFound', 'processingFailure',
}


def provider_reason(response):
    """Extract only allowlisted error identifiers, never provider prose or request data."""
    try:
        error = response.json().get('error')
        if isinstance(error, str):
            candidates = [error]
        elif isinstance(error, dict):
            candidates = [error.get('status')]
            candidates += [item.get('reason') for item in error.get('errors', []) if isinstance(item, dict)]
            candidates += [item.get('reason') for item in error.get('details', []) if isinstance(item, dict)]
        else:
            candidates = []
        reasons = sorted({v for v in candidates if isinstance(v, str) and v in SAFE_REASONS})
        return ','.join(reasons) or 'unrecognized_provider_error'
    except (ValueError, AttributeError, TypeError):
        return 'unrecognized_provider_error'


def oauth_failure(stage, reason, status=None, hint='Try connecting again.'):
    diagnostic = uuid.uuid4().hex[:12]
    logger.warning('YouTube OAuth failed diagnostic=%s step=%s http_status=%s reason=%s',
                   diagnostic, stage, status if status is not None else 'none', reason)
    raise HTTPException(502, f'YouTube connection failed at {stage} ({reason}). {hint} Diagnostic: {diagnostic}')


def check_oauth_response(response, stage):
    if not response.is_success:
        reason = provider_reason(response)
        hint = 'Check the backend Google OAuth client and redirect URI configuration.' if stage == 'token_exchange' else 'Check YouTube Data API v3 is enabled in the OAuth client project and review its API restrictions.'
        oauth_failure(stage, reason, response.status_code, hint)
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except ValueError:
        oauth_failure(stage, 'invalid_response', response.status_code)


class OAuthAccessLogFilter(logging.Filter):
    """Uvicorn normally logs callback query strings, including authorization codes."""
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].split('?', 1)[0] == '/api/social/youtube/callback':
                args[2] = '/api/social/youtube/callback'
                record.args = tuple(args)
        return True


def start_worker(target, args):
    threading.Thread(target=target, args=args, daemon=True).start()


SCOPES = 'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.force-ssl'


def config():
    names = ('GOOGLE_YOUTUBE_CLIENT_ID', 'GOOGLE_YOUTUBE_CLIENT_SECRET', 'GOOGLE_YOUTUBE_REDIRECT_URI', 'SOCIAL_TOKEN_ENCRYPTION_KEY')
    values = [os.getenv(n, '') for n in names]
    if not all(values):
        raise HTTPException(503, 'YouTube is not configured. Ask the administrator to configure Google OAuth and token encryption.')
    try:
        Fernet(values[3].encode())
    except ValueError:
        raise HTTPException(503, 'YouTube token encryption key is invalid.')
    return values


@contextmanager
def db():
    path = Path(os.getenv('SOCIAL_DATABASE_PATH', 'video_jobs/social.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, key TEXT, value TEXT, PRIMARY KEY(kind,key))')
    connection.commit()
    os.chmod(path, 0o600)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def read(kind, key):
    with db() as c:
        row = c.execute('SELECT value FROM records WHERE kind=? AND key=?', (kind, key)).fetchone()
    return json.loads(row[0]) if row else None


def write(kind, key, value):
    with db() as c:
        c.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', (kind, key, json.dumps(value)))


def protect(value):
    return Fernet(config()[3].encode()).encrypt(json.dumps(value).encode()).decode()


def unseal(record):
    try:
        return json.loads(Fernet(config()[3].encode()).decrypt(record['token'].encode()))
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(409, 'YouTube credentials cannot be read. Reconnect your channel.')


def credentials(user, transaction=None):
    record = read('connection', user)
    if not record:
        raise HTTPException(409, 'Connect YouTube before publishing.')
    token = unseal(record)
    if token.get('expires_at', 0) < time.time()+60:
        if not token.get('refresh_token'):
            raise HTTPException(409, 'YouTube offline authorization is missing. Reconnect your channel.')
        try:
            response = httpx.post('https://oauth2.googleapis.com/token', data={'client_id': config()[0], 'client_secret': config()[1], 'grant_type': 'refresh_token', 'refresh_token': token['refresh_token']}, timeout=30)
        except httpx.RequestError:
            raise HTTPException(503, 'Unable to reach Google authorization. Retry when your backend connection is restored.')
        if response.status_code != 200:
            raise HTTPException(409, 'YouTube authorization expired or was revoked. Reconnect YouTube.')
        token.update(response.json());token['expires_at'] = time.time()+token.get('expires_in', 3600)
        renewed = {**record, 'token': protect(token)}
        if transaction is not None:
            transaction.execute('UPDATE records SET value=? WHERE kind=? AND key=?', (json.dumps(renewed), 'connection', user))
        else:
            write('connection', user, renewed)
    return token['access_token']


class PendingConfirmation(Exception):
    pass


@contextmanager
def schedule_lock(key):
    # Lock survives database commits used to durably save mutation intent.
    database = Path(os.getenv('SOCIAL_DATABASE_PATH', 'video_jobs/social.sqlite3'))
    directory = database.parent/'social-locks'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory/hashlib.sha256(key.encode()).hexdigest()).open('a+b') as handle:
        if os.name == 'nt':
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def youtube_data(response, step):
    if not response.is_success:
        reason = provider_reason(response)
        logger.warning('YouTube request failed step=%s http_status=%s reason=%s', step, response.status_code, reason)
        hint = 'Reconnect YouTube to refresh permissions.' if response.status_code == 401 or 'insufficientPermissions' in reason else 'Check your channel and OAuth project API permissions, restrictions and quota in Google Cloud and YouTube Studio.'
        raise HTTPException(502, f'YouTube {step} failed (HTTP {response.status_code}: {reason}). {hint}')
    return response.json()


def connection_for(record, manage=False, transaction=None):
    connection = read('connection', record['user'])
    if record.get('channel_id') and (not connection or connection.get('channel_id') != record['channel_id']):
        raise HTTPException(409, 'The connected YouTube channel changed. Reconnect the channel used for this upload before continuing.')
    if manage:
        if not connection:
            raise HTTPException(409, 'Reconnect YouTube to enable native scheduling.')
        token = unseal(connection)
        if scheduling.UPDATE_SCOPE not in token.get('scope', '').split():
            raise HTTPException(409, 'Reconnect YouTube and grant video management permission to enable scheduling, changes and cancellation.')
    return credentials(record['user'], transaction=transaction)


def remote_video(record, manage=False, transaction=None):
    access = connection_for(record, manage, transaction=transaction)
    try:
        response = httpx.get('https://www.googleapis.com/youtube/v3/videos', params={'part': 'processingDetails,status,snippet', 'id': record['video_id']}, headers={'Authorization': 'Bearer '+access}, timeout=30)
    except httpx.RequestError:
        raise HTTPException(503, 'Unable to reach YouTube to check this upload. Refresh after the backend connection is restored.')
    data = youtube_data(response, 'video lookup')
    if not data.get('items'):
        raise HTTPException(409, 'YouTube did not return this uploaded video. Check the connected channel and YouTube Studio. No new upload will be started.')
    item = data['items'][0]
    if record.get('channel_id') and item.get('snippet', {}).get('channelId') != record['channel_id']:
        raise HTTPException(409, 'YouTube returned a video from a different channel. Reconnect the original channel.')
    return item


def write_remote_schedule(record, schedule, item, transaction=None):
    access = connection_for(record, manage=True, transaction=transaction)
    if schedule:
        scheduling.validate_lead(schedule)
        if item.get('status', {}).get('privacyStatus') != 'private' or record.get('ever_public'):
            raise HTTPException(409, 'Only a private video that has never been published can be scheduled. This video will not be uploaded again.')
    payload = {'id': record['video_id'], 'status': scheduling.status_payload(item.get('status', {}), schedule['publish_at'] if schedule else None)}
    response = httpx.put('https://www.googleapis.com/youtube/v3/videos', params={'part': 'status'}, headers={'Authorization': 'Bearer '+access}, json=payload, timeout=30)
    youtube_data(response, 'schedule update' if schedule else 'schedule cancellation')
    # An accepted mutation alone is not a confirmed schedule. Read it back.
    try:
        verified = remote_video(record, manage=True, transaction=transaction)
    except (HTTPException, httpx.RequestError) as exc:
        raise PendingConfirmation() from exc
    if not scheduling.matches(verified.get('status', {}), schedule['publish_at'] if schedule else None):
        raise PendingConfirmation()
    return verified


class ScheduleChange(BaseModel):
    schedule: scheduling.Schedule | None = None
    revision: int = Field(ge=0)


class Publish(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=5000)
    privacy: Literal['private', 'unlisted', 'public'] = 'private'
    submission_id: uuid.UUID
    edit: dict
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    schedule: scheduling.Schedule | None = None


def register(app, integration, selected, export, export_model):
    lock = threading.Lock()
    access_logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(f, OAuthAccessLogFilter) for f in access_logger.filters):
        access_logger.addFilter(OAuthAccessLogFilter())

    @app.get('/api/projects/{pid}/social/youtube')
    def connection(pid: str, request: Request):
        integration.require_project(pid, request.state.user_id)
        rec = read('connection', request.state.user_id)
        can_schedule = False
        if rec:
            try:
                token = json.loads(Fernet(config()[3].encode()).decrypt(rec['token'].encode()))
                can_schedule = scheduling.UPDATE_SCOPE in token.get('scope', '').split()
            except (InvalidToken, ValueError, KeyError):
                raise HTTPException(409, 'YouTube credentials cannot be read. Reconnect your channel.')
        return {'connected': bool(rec), 'channel': rec['channel'] if rec else None, 'can_schedule': can_schedule}

    @app.post('/api/projects/{pid}/social/youtube/connect')
    def connect(pid: str, request: Request):
        integration.require_project(pid, request.state.user_id)
        client, _, redirect, _ = config()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        write('oauth', state, {'user': request.state.user_id, 'expires': time.time()+600, 'verifier': verifier})
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return {'url': 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id': client, 'redirect_uri': redirect, 'response_type': 'code', 'scope': SCOPES, 'state': state, 'access_type': 'offline', 'prompt': 'consent', 'code_challenge': challenge, 'code_challenge_method': 'S256'})}

    @app.get('/api/social/youtube/callback')
    def callback(state: str = '', code: str = '', error: str = ''):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT value FROM records WHERE kind='oauth' AND key=?", (state,)).fetchone()
            c.execute("DELETE FROM records WHERE kind='oauth' AND key=?", (state,))
        rec = json.loads(row[0]) if row else None
        if not rec or rec['expires'] < time.time():
            raise HTTPException(400, 'Invalid or expired YouTube connection request. Connect again from Cascade.')
        if error or not code:
            return HTMLResponse('YouTube connection was cancelled. Return to Cascade and try again.', status_code=400)
        client, secret, redirect, _ = config()
        stage = 'token_exchange'
        try:
            response = httpx.post('https://oauth2.googleapis.com/token', data={'client_id': client, 'client_secret': secret, 'redirect_uri': redirect, 'code': code, 'code_verifier': rec['verifier'], 'grant_type': 'authorization_code'}, timeout=30)
            token = check_oauth_response(response, stage)
            stage = 'scope_validation'
            if not isinstance(token.get('scope', ''), str):
                oauth_failure(stage, 'invalid_scope_response')
            granted = set(token.get('scope', '').split())
            missing = set(SCOPES.split()) - granted
            # These are fixed scope names and boolean facts, never token values.
            logger.warning('YouTube OAuth token_exchange succeeded upload_scope=%s readonly_scope=%s management_scope=%s refresh_token_present=%s',
                           SCOPES.split()[0] in granted, SCOPES.split()[1] in granted, scheduling.UPDATE_SCOPE in granted, bool(token.get('refresh_token')))
            if missing:
                oauth_failure(stage, 'missing_required_scopes', hint='Reconnect and grant YouTube upload, read and video management permissions.')
            if not token.get('access_token'):
                oauth_failure('token_exchange', 'missing_access_token')
            if not token.get('refresh_token'):
                oauth_failure('offline_access', 'missing_refresh_token', hint='Google did not return offline access. Reconnect with consent; if this persists, remove Cascade from your Google account connections and reconnect.')
            stage = 'channel_lookup'
            channel = httpx.get('https://www.googleapis.com/youtube/v3/channels', params={'part': 'snippet', 'mine': 'true'}, headers={'Authorization': 'Bearer '+token['access_token']}, timeout=30)
            channel_data = check_oauth_response(channel, stage)
            items = channel_data.get('items', [])
            if not items:
                oauth_failure(stage, 'no_channel_returned', channel.status_code, 'Google returned no channel for the authorized identity. Reconnect and select the intended YouTube channel or Brand Account.')
            channel_id = items[0]['id']
            channel_title = items[0]['snippet']['title']
            stage = 'credential_storage'
            token['expires_at'] = time.time()+token.get('expires_in', 3600)
            write('connection', rec['user'], {'token': protect(token), 'channel': channel_title, 'channel_id': channel_id})
        except httpx.RequestError:
            oauth_failure(stage, 'network_error', hint='The backend could not reach Google. Check network access and retry.')
        except (ValueError, KeyError, TypeError, IndexError):
            oauth_failure(stage, 'invalid_response')
        except (sqlite3.Error, OSError):
            oauth_failure(stage, 'storage_error', hint='Check the backend social database path and filesystem permissions.')
        logger.warning('YouTube OAuth connected successfully')
        return HTMLResponse('YouTube connected. Return to Cascade and click Refresh connection. You may close this tab.')

    def job_key(pid, jid, index, user):
        return user+':'+pid+':'+jid+':'+str(index)

    def public(record):
        # Full edit/caption overlay snapshots remain backend-only.
        return {k: v for k, v in record.items() if k not in ('snapshot', 'user', 'worker_pid', 'channel_token')}

    def reconcile(key):
        # Serialize read/modify/verify across processes, including browser GET and worker polling.
        with schedule_lock(key), db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT value FROM records WHERE kind='publish' AND key=?", (key,)).fetchone()
            rec = json.loads(row[0]) if row else None
            if not rec or not rec.get('video_id') or rec['status'] not in ('Processing', 'Scheduled', 'Verifying'):
                return rec
            try:
                if rec.get('schedule') and rec['status']=='Processing' and not rec.get('pending_change'):
                    scheduling.validate_lead(rec['schedule'])
                item = remote_video(rec, manage=bool(rec.get('schedule')), transaction=c)
                remote = item.get('status', {})
                processing = item.get('processingDetails', {}).get('processingStatus')
                if remote.get('privacyStatus') == 'public':
                    rec['ever_public'] = True
                if processing in ('failed', 'terminated') or remote.get('uploadStatus') in ('failed', 'rejected', 'deleted'):
                    raise HTTPException(409, 'YouTube rejected or failed to process this video. Review YouTube Studio; this video will not be uploaded again.')
                if rec.get('pending_change'):
                    target = rec['pending_change']['schedule']
                    # Resolve ambiguous update responses via GET, never repeating an upload.
                    if scheduling.matches(remote, target['publish_at'] if target else None):
                        rec.update(schedule=target, status='Scheduled' if target else 'Private', revision=rec.get('revision', 0)+1)
                        rec.pop('pending_change', None);rec.pop('error', None);rec.pop('message', None)
                    else:
                        rec.update(status='Failed', error=rec.get('error') or 'YouTube has not confirmed the last schedule change. Check YouTube Studio, then retry the change or cancel. The existing upload is retained.')
                        rec.pop('pending_change', None)
                elif rec.get('schedule'):
                    schedule = rec['schedule']
                    if rec['status'] == 'Scheduled':
                        if remote.get('privacyStatus') == 'public':
                            rec.update(status='Published');rec.pop('error', None)
                        elif not scheduling.matches(remote, schedule['publish_at']):
                            raise HTTPException(409, 'The schedule changed or was removed on YouTube. Review YouTube Studio or choose a new time.')
                    elif processing == 'succeeded':
                        scheduling.validate_lead(schedule)
                        # Persist intent BEFORE mutating YouTube for crash/timeout reconciliation.
                        rec['pending_change'] = {'schedule': schedule}
                        c.execute('UPDATE records SET value=? WHERE kind=? AND key=?', (json.dumps(rec), 'publish', key))
                        c.commit();c.execute('BEGIN IMMEDIATE')
                        write_remote_schedule(rec, schedule, item, transaction=c)
                        rec.update(status='Scheduled', revision=rec.get('revision', 0)+1)
                        rec.pop('pending_change', None);rec.pop('error', None);rec.pop('message', None)
                    else:
                        scheduling.validate_lead(schedule)
                elif processing == 'succeeded':
                    rec['status'] = 'Published' if rec.get('privacy', 'private') != 'private' else 'Private'
                    rec.pop('error', None)
            except (httpx.RequestError, HTTPException, InvalidToken, PendingConfirmation) as exc:
                if rec.get('pending_change') and isinstance(exc, (httpx.RequestError, PendingConfirmation)):
                    rec.update(status='Verifying', error='Schedule confirmation is pending. Check YouTube Studio before changing it; no new upload will be attempted.')
                elif isinstance(exc, HTTPException):
                    rec.update(status='Failed', error=exc.detail)
                    rec.pop('pending_change', None)
                else:
                    rec['error'] = 'Unable to check YouTube. Reconnect the original channel and refresh. No duplicate upload will be attempted.'
            c.execute('UPDATE records SET value=? WHERE kind=? AND key=?', (json.dumps(rec), 'publish', key))
            return rec

    def finish_processing(key):
        # This worker only completes the upload transaction. YouTube owns the future publication.
        for _ in range(720):
            rec = reconcile(key)
            if not rec or rec['status'] not in ('Processing', 'Verifying'):
                return
            time.sleep(10)
        rec = read('publish', key)
        if rec and rec['status'] in ('Processing', 'Verifying'):
            rec['error'] = 'Processing is taking longer than expected. Reopen the panel to check again. The upload is retained; the schedule is not confirmed.'
            write('publish', key, rec)

    def resume_processing():
        with db() as c:
            rows = c.execute("SELECT key,value FROM records WHERE kind='publish'").fetchall()
        for key, value in rows:
            rec = json.loads(value)
            if (rec.get('schedule') or rec.get('pending_change')) and rec.get('video_id') and rec.get('status') in ('Processing', 'Verifying'):
                start_worker(finish_processing, (key,))
    app.router.add_event_handler('startup', resume_processing)

    def run(key, record, body, request):
        response = None
        upload_attempted = False
        def update(**values):
            record.update(values);write('publish', key, record)
        try:
            connection_for(record, manage=bool(record.get('schedule')))
            response = export(record['pid'], record['jid'], record['index'], export_model.model_validate(body.edit), request)
            if record.get('schedule'):
                scheduling.validate_lead(record['schedule'])
            access = connection_for(record, manage=bool(record.get('schedule')))
            update(status='Uploading')
            headers = {'Authorization': 'Bearer '+access}
            with httpx.Client(timeout=120) as client:
                # Keep scheduled uploads unarmed while processing: past publishAt publishes immediately.
                privacy = 'private' if record.get('schedule') else body.privacy
                start = client.post('https://www.googleapis.com/upload/youtube/v3/videos', params={'uploadType': 'resumable', 'part': 'snippet,status'}, headers={**headers, 'X-Upload-Content-Type': 'video/mp4', 'X-Upload-Content-Length': str(Path(response.path).stat().st_size)}, json={'snippet': {'title': body.title, 'description': body.description}, 'status': {'privacyStatus': privacy}})
                youtube_data(start, 'upload initialization'); location = start.headers['location']
                if not location.startswith('https://www.googleapis.com/'):
                    raise ValueError('Unexpected upload endpoint')
                # Persist ambiguity BEFORE sending media. Never automatically duplicate this upload.
                upload_attempted = True;update(upload_attempted=True)
                with open(response.path, 'rb') as media:
                    uploaded = client.put(location, headers={**headers, 'Content-Type': 'video/mp4', 'Content-Length': str(Path(response.path).stat().st_size)}, content=media)
                data = youtube_data(uploaded, 'upload');video_id = data['id']
            update(status='Processing', video_id=video_id, url='https://www.youtube.com/watch?v='+video_id)
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else 'YouTube upload failed. Check your channel permissions, authorization and API quota.'
            if upload_attempted:
                detail += ' The upload may have reached YouTube. Check YouTube Studio; duplicate retries are blocked.'
            update(status='Failed', error=detail, upload_attempted=upload_attempted)
        finally:
            if response and response.background:
                response.background.func(*response.background.args, **response.background.kwargs)
        if record.get('video_id') and record.get('schedule'):
            start_worker(finish_processing, (key,))

    @app.post('/api/projects/{pid}/editor/{jid}/{index}/publish/youtube')
    def publish(pid: str, jid: str, index: int, body: Publish, request: Request):
        selected(pid, jid, index, request.state.user_id)
        edit = export_model.model_validate(body.edit)
        key = job_key(pid, jid, index, request.state.user_id)
        # Return persisted submissions before validating a now-expired original schedule.
        with lock, schedule_lock(key), db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT value FROM records WHERE kind='publish' AND key=?", (key,)).fetchone()
            previous = json.loads(row[0]) if row else None
            if previous and (previous['submission_id'] == str(body.submission_id) or previous.get('video_id') or previous.get('upload_attempted') or previous['status'] != 'Failed'):
                return public(previous)
            schedule = scheduling.resolve(body.schedule) if body.schedule else None
            if schedule and body.privacy != 'private':
                raise HTTPException(422, 'Scheduled videos upload as Private and become Public at the selected time. Unlisted scheduling is not supported.')
            connection = read('connection', request.state.user_id) or {}
            record = {'user': request.state.user_id, 'pid': pid, 'jid': jid, 'index': index, 'submission_id': str(body.submission_id), 'status': 'Rendering', 'started': time.time(), 'worker_pid': os.getpid(), 'revision': 0, 'schedule': schedule, 'privacy': body.privacy, 'ever_public': body.privacy == 'public' and not schedule, 'channel': connection.get('channel'), 'channel_id': connection.get('channel_id'), 'snapshot': {'edit': edit.model_dump(), 'title': body.title, 'description': body.description, 'hashtags': body.hashtags, 'channel': connection.get('channel'), 'channel_id': connection.get('channel_id'), 'schedule': schedule}}
            if schedule and not record['channel_id']:
                raise HTTPException(409, 'Reconnect YouTube to identify and authorize your channel for scheduling.')
            connection_for(record, manage=bool(schedule), transaction=c)
            c.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', ('publish', key, json.dumps(record)))
        start_worker(run, (key, record, body, request))
        return public(record)

    @app.get('/api/projects/{pid}/editor/{jid}/{index}/publish/youtube')
    def status(pid: str, jid: str, index: int, request: Request):
        selected(pid, jid, index, request.state.user_id)
        key = job_key(pid, jid, index, request.state.user_id)
        rec = read('publish', key)
        if not rec:
            return {'status': 'Ready'}
        if rec['status'] in ('Rendering', 'Uploading'):
            try:
                os.kill(rec.get('worker_pid', os.getpid()), 0)
            except ProcessLookupError:
                rec.update(status='Failed', error='The publishing worker was interrupted. Check YouTube Studio; duplicate upload retries are blocked.', upload_attempted=rec.get('upload_attempted', rec['status'] == 'Uploading'))
                write('publish', key, rec)
        if rec['status'] in ('Processing', 'Scheduled', 'Verifying'):
            rec = reconcile(key)
        return public(rec)

    @app.put('/api/projects/{pid}/editor/{jid}/{index}/publish/youtube/schedule')
    def change_schedule(pid: str, jid: str, index: int, body: ScheduleChange, request: Request):
        selected(pid, jid, index, request.state.user_id)
        key = job_key(pid, jid, index, request.state.user_id)
        schedule = scheduling.resolve(body.schedule) if body.schedule else None
        # Lock across provider mutation and read-back so competing clients cannot clobber it.
        with lock, schedule_lock(key), db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT value FROM records WHERE kind='publish' AND key=?", (key,)).fetchone()
            rec = json.loads(row[0]) if row else None
            if not rec or not rec.get('video_id'):
                raise HTTPException(409, 'No uploaded video is available to manage.')
            if rec.get('revision', 0) != body.revision:
                raise HTTPException(409, 'The schedule changed in another session. Refresh and try again.')
            if rec['status'] in ('Rendering', 'Uploading', 'Processing'):
                raise HTTPException(409, 'Wait for YouTube processing to finish before changing the schedule.')
            item = remote_video(rec, manage=True, transaction=c)
            if schedule and item.get('processingDetails', {}).get('processingStatus') != 'succeeded':
                raise HTTPException(409, 'YouTube has not finished processing. Check YouTube Studio before scheduling.')
            rec['pending_change'] = {'schedule': schedule}
            rec['status'] = 'Verifying'
            c.execute('UPDATE records SET value=? WHERE kind=? AND key=?', (json.dumps(rec), 'publish', key))
            c.commit();c.execute('BEGIN IMMEDIATE')
            try:
                write_remote_schedule(rec, schedule, item, transaction=c)
                rec.update(schedule=schedule, status='Scheduled' if schedule else 'Private', revision=rec.get('revision', 0)+1)
                rec.pop('pending_change', None);rec.pop('error', None);rec.pop('message', None)
                if not schedule:
                    rec['message'] = 'Schedule canceled. Your uploaded video is Private and will not publish automatically.'
            except HTTPException as exc:
                rec.update(status='Failed', error=exc.detail)
                rec.pop('pending_change', None)
            except (httpx.RequestError, PendingConfirmation):
                rec['error'] = 'YouTube did not confirm the change. Check YouTube Studio and refresh; no new upload will be attempted.'
                # Preserve intent for read-back reconciliation after ambiguous responses.
            c.execute('UPDATE records SET value=? WHERE kind=? AND key=?', (json.dumps(rec), 'publish', key))
            return public(rec)
