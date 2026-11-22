"""Signed media links, so the browser can stream a protected video in pieces.

A <video> or <audio> tag cannot send the sign-in header, so the frontend used to download every video whole
and play the in-memory copy. Instead it asks for a link (GET /api/media-link?path=...): the link carries an
encrypted token naming that one path and the signed-in user, and expires after LINK_HOURS. The file route
still checks that the user owns the file; the token only stands in for the sign-in header on that one path.

The key is CASCADE_MEDIA_SECRET when set (any text), otherwise a random key kept in video_jobs/.media_key so
links survive a backend restart.
"""
import base64
import hashlib
import json
import os
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request

from .config import JOBS_DIR

LINK_HOURS = 6
PARAM = 'media_token'
STREAMABLE = ('/clips/', '/api/projects/')   # only GET media routes under these are ever signed


def _fernet():
    secret = os.getenv('CASCADE_MEDIA_SECRET', '').strip()
    if secret:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    else:
        path = JOBS_DIR/'.media_key'
        if not path.is_file():
            path.write_bytes(Fernet.generate_key())
            path.chmod(0o600)
        key = path.read_bytes().strip()
    return Fernet(key)


def sign(path, user_id):
    return _fernet().encrypt(json.dumps({'p': path, 'u': user_id}).encode()).decode()


def user_for(token, path):
    """The user a token was issued to, when it is valid for exactly this path; else None."""
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
