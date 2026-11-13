"""Single-request Gemini planning for the AI Editor, restricted to the free tier.

The API key is read from the backend environment (Cascade's .env) and is never
logged, returned, or passed to OpenChatCut. Only free-tier text models are
allowed; there is no paid or alternative-provider fallback. Quota exhaustion is
reported to the user with the reset time and leaves the timeline untouched.
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

LOG = logging.getLogger(__name__)
API = 'https://generativelanguage.googleapis.com/v1beta'
# Gemini API free tier with tool/structured-output support, verified 2026-11-02
# against Google's pricing page and a live tool-calling check.
FREE_MODELS = ('gemini-3.6-flash', 'gemini-3.8-flash', 'gemini-3.5-flash-lite', 'gemini-3-flash-preview')
FREE_DAILY_REQUESTS = 20  # GenerateRequestsPerDayPerProjectPerModel-FreeTier observed for gemini-3.6-flash
PACIFIC = ZoneInfo('America/Los_Angeles')
_lock = threading.Lock()
_last = threading.local()


class QuotaError(HTTPException):
    def __init__(self, message):
        super().__init__(429, message)


def model():
    name = os.getenv('CASCADE_EDITOR_GEMINI_MODEL', FREE_MODELS[0]).strip()
    if name not in FREE_MODELS:
        raise HTTPException(503, f'{name} is not an allowed Gemini free-tier model. Paid models are disabled for the AI Editor.')
    return name


def configured():
    return bool(os.getenv('GEMINI_API_KEY', '').strip())


def _key():
    key = os.getenv('GEMINI_API_KEY', '').strip().strip('"\'')
    if not key:
        raise HTTPException(503, 'The AI Editor needs GEMINI_API_KEY in the backend .env (free tier, no billing). Restart the backend after adding it.')
    return key


def _ledger_path():
    from backend.core.config import PROJECT_DIR
    return Path(os.getenv('CASCADE_EDITOR_AI_USAGE', PROJECT_DIR/'video_jobs'/'.editor-ai-usage.json'))


def _pacific_day():
    return datetime.now(PACIFIC).strftime('%Y-%m-%d')


def reset_time_text():
    now = datetime.now(PACIFIC)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    local = reset.astimezone()
    return local.strftime('%-I:%M %p %Z')


def usage():
    """Requests Cascade has sent today per model (Pacific day, matching Google's reset)."""
    try:
        data = json.loads(_ledger_path().read_text())
    except (OSError, ValueError):
        data = {}
    day = _pacific_day()
    used = data.get(day, {})
    name = os.getenv('CASCADE_EDITOR_GEMINI_MODEL', FREE_MODELS[0])
    exhausted = data.get('exhausted', {}).get(day, {}).get(name, False)
    return {'model': name, 'used': used.get(name, 0), 'limit': FREE_DAILY_REQUESTS, 'exhausted': exhausted, 'resets': reset_time_text()}


def _record(name, exhausted=False):
    with _lock:
        path = _ledger_path()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        day = _pacific_day()
        data = {k: v for k, v in data.items() if k in (day, 'exhausted')}
        data.setdefault(day, {})
        data[day][name] = data[day].get(name, 0) + (0 if exhausted else 1)
        if exhausted:
            data.setdefault('exhausted', {}).setdefault(day, {})[name] = True
        data['exhausted'] = {d: v for d, v in data.get('exhausted', {}).items() if d == day}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data))
        os.replace(tmp, path)


def _quota(error):
    """('day'|'minute', retry seconds) from Google's RESOURCE_EXHAUSTED details."""
    daily, delay = False, None
    for detail in error.get('details', []) or []:
        for violation in detail.get('violations', []) or []:
            if re.search(r'PerDay', str(violation.get('quotaId', ''))):
                daily = True
        match = re.fullmatch(r'([\d.]+)s', str(detail.get('retryDelay', '')))
        if match:
            delay = float(match.group(1))
    return ('day' if daily else 'minute'), delay


def generate_json(system, parts, schema, *, max_output_tokens=4096):
    """One generateContent call returning parsed JSON. `parts` are Gemini content parts.
    With schema=None, JSON mode is used and the caller validates (for schemas too large
    for Gemini's structured-output subset)."""
    name = model()
    key = _key()
    if usage()['exhausted']:
        raise QuotaError(f'The Gemini free daily quota for {name} is used up. Nothing was changed. It resets at {reset_time_text()} (midnight Pacific).')
    body = {
        'systemInstruction': {'parts': [{'text': system}]},
        'contents': [{'role': 'user', 'parts': parts}],
        'generationConfig': {'responseMimeType': 'application/json', **({'responseJsonSchema': schema} if schema else {}),
                             'temperature': .4, 'maxOutputTokens': max_output_tokens},
    }
    # Overload (503) is capacity, not quota: fail over across FREE models only. A daily
    # quota stop is never routed around, and there is no paid or other-provider fallback.
    candidates = [name] + [m for m in FREE_MODELS if m != name and not _exhausted(m)]
    overloaded = []
    for current in candidates:
        response = _post(current, key, body)
        if response.status_code == 503:
            overloaded.append(current)
            LOG.warning('AI Editor gemini overloaded model=%s; trying next free model', current)
            continue
        break
    else:
        raise HTTPException(503, f"All free Gemini models are temporarily overloaded ({', '.join(overloaded)}). Nothing was changed; retry in a few minutes.")
    if response.status_code >= 400:
        LOG.warning('AI Editor gemini request failed stage=http status=%s model=%s', response.status_code, current)
        if response.status_code in (401, 403):
            raise HTTPException(503, 'Gemini rejected the configured API key. Check GEMINI_API_KEY in the backend .env (free-tier project).')
        raise HTTPException(502, 'Gemini could not produce an editing plan for this request. Nothing was changed; try rephrasing.')
    try:
        candidate = response.json()['candidates'][0]
        text = ''.join(p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought'))
        if candidate.get('finishReason') not in (None, 'STOP'):
            raise ValueError(candidate.get('finishReason'))
        _last.model = current
        return json.loads(text)
    except (KeyError, IndexError, ValueError, TypeError):
        LOG.warning('AI Editor gemini request failed stage=parse model=%s', current)
        raise HTTPException(502, 'Gemini returned an incomplete editing plan. Nothing was changed; try a shorter request.') from None


def _exhausted(name):
    try:
        data = json.loads(_ledger_path().read_text())
    except (OSError, ValueError):
        return False
    return bool(data.get('exhausted', {}).get(_pacific_day(), {}).get(name))


def _post(name, key, body):
    """One model: a single request, plus one wait for a short per-minute limit."""
    for attempt in range(2):
        try:
            with httpx.Client(timeout=httpx.Timeout(120, connect=10), trust_env=False) as client:
                response = client.post(f'{API}/models/{name}:generateContent', headers={'x-goog-api-key': key}, json=body)
        except httpx.HTTPError:
            LOG.warning('AI Editor gemini request failed stage=network model=%s', name)
            raise HTTPException(503, 'Could not reach Gemini. Check the internet connection and retry; nothing was changed.') from None
        if response.status_code != 429:
            _record(name)
            return response
        try:
            error = response.json().get('error', {})
        except ValueError:
            error = {}
        kind, delay = _quota(error)
        if kind == 'day':
            _record(name, exhausted=True)
            LOG.warning('AI Editor gemini quota exhausted scope=day model=%s', name)
            raise QuotaError(f'The Gemini free daily quota for {name} ({FREE_DAILY_REQUESTS} requests) is used up. Nothing was changed and earlier edits are kept. It resets at {reset_time_text()} (midnight Pacific).')
        _record(name)
        if attempt == 0 and delay is not None and delay <= 45:
            LOG.info('AI Editor gemini per-minute limit; waiting %.0fs model=%s', delay, name)
            time.sleep(delay + 1)
            continue
        raise QuotaError('Gemini free-tier per-minute limit reached. Nothing was changed; wait a minute and send the request again.')


def last_model():
    return getattr(_last, 'model', None) or model()


def image_part(jpeg_b64):
    return {'inlineData': {'mimeType': 'image/jpeg', 'data': jpeg_b64}}


def text_part(text):
    return {'text': text}


