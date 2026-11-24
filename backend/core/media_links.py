"""Signed media links, so the browser can stream a protected video in pieces.

A <video> or <audio> tag cannot send the sign-in header, so the frontend used to download every video whole
and play the in-memory copy. Instead it asks for a link (GET /api/media-link?path=...): the link carries an
encrypted token naming that one path and the signed-in user, and expires after LINK_HOURS. The file route
still checks that the user owns the file; the token only stands in for the sign-in header on that one path.

The key is CASCADE_MEDIA_SECRET when set (any text), otherwise a random key kept in video_jobs/.media_key so
links survive a backend restart.

Every Fernet link is different, even for the same file, so a browser can never reuse what it fetched. For small
pictures that should be cached (the Projects page thumbnails) `cacheable_link` makes a link that stays the same
for a whole day instead: "c.<user>.<expiry>.<signature>", the signature an HMAC of path, user and expiry.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request

from .config import JOBS_DIR

LINK_HOURS = 6
PARAM = 'media_token'
STREAMABLE = ('/clips/', '/api/projects/')   # only GET media routes under these are ever signed


def _key():
    secret = os.getenv('CASCADE_MEDIA_SECRET', '').strip()
    if secret:
        return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    path = JOBS_DIR/'.media_key'
    if not path.is_file():
        path.write_bytes(Fernet.generate_key())
        path.chmod(0o600)
    return path.read_bytes().strip()


def _fernet():
    return Fernet(_key())


def _signature(path, user_id, expires):
    secret = hashlib.sha256(b'cacheable-media-link:' + _key()).digest()
    return hmac.new(secret, f'{path}\n{user_id}\n{expires}'.encode(), hashlib.sha256).hexdigest()[:40]


def sign(path, user_id):
    return _fernet().encrypt(json.dumps({'p': path, 'u': user_id}).encode()).decode()


def cacheable_link(path, user_id, now=None):
    """A link to `path` that is the same all day (valid for one to two days), so the browser can cache the file."""
    expires = (int((now or time.time()) // 86400) + 2) * 86400
    user = base64.urlsafe_b64encode(user_id.encode()).decode().rstrip('=')
    return f'{path}?{PARAM}=c.{user}.{expires}.{_signature(path, user_id, expires)}'


def _cacheable_user(token, path):
    try:
        _, user, expires, signature = token.split('.')
        user_id = base64.urlsafe_b64decode(user + '=' * (-len(user) % 4)).decode()
        expires = int(expires)
    except ValueError:
        return None
    if expires < time.time() or not hmac.compare_digest(signature, _signature(path, user_id, expires)):
        return None
    return user_id


def user_for(token, path):
    """The user a token was issued to, when it is valid for exactly this path; else None."""
    if token.startswith('c.'):
        return _cacheable_user(token, path)
    try:
        data = json.loads(_fernet().decrypt(token.encode(), ttl=LINK_HOURS*3600))
    except (InvalidToken, ValueError):
        return None
    return data.get('u') if data.get('p') == path else None


def media_link(path: str, request: Request):
    """GET /api/media-link?path=/api/projects/.../media -> {"url": the same path with a token, to stream}."""
    if not path.startswith(STREAMABLE) or '?' in path or '..' in path:
        raise HTTPException(422, 'Invalid media address.')
    return {'url': f'{path}?{PARAM}={quote(sign(path, request.state.user_id))}', 'expires_in': LINK_HOURS*3600}
