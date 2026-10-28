"""Owner-checked social copy based on the saved editor trim."""
import hashlib
import json
from fastapi import Request
from backend.services.social_copy import CopyRequest, generate_social_copy


def register(app, integration, selected, details, draft_path):
    @app.post('/api/projects/{pid}/clips/{jid}/{index}/social-copy')
    def social_copy(pid: str, jid: str, index: int, body: CopyRequest, request: Request, refresh: bool = False):
        user = request.state.user_id
        clip = selected(pid, jid, index, user)
        info = details(jid, clip)
        host = integration.host
        draft = draft_path(pid, jid, index, user)
        with integration.lock:
            state = host.load_json(draft).get('state', {}) if host.metadata_exists(draft) else {}
            start, end = state.get('start', 0), state.get('end', info['duration'])
            cues = [{**cue, 'text': state.get('texts', {}).get(str(number), cue['text'])}
                    for number, cue in enumerate(info['cues']) if cue['end'] > start and cue['start'] < end]
            settings_path = integration.project_dir(user)/'settings'/'preferences.json'
            settings = host.load_json(settings_path) if host.metadata_exists(settings_path) else {}
            owner = host.load_json(host.JOBS_DIR/jid/'owner.json')
            context = {'title': clip.get('title', ''), 'transcript': cues,
                       'trim': [start, end], 'session_prompt': owner.get('prompt', ''), 'settings': settings}
            platforms = sorted(set(body.platforms))
            key = hashlib.sha256(json.dumps({'platforms': platforms, 'vibe': body.vibe,
                'context': context, 'version': 1}, sort_keys=True).encode()).hexdigest()
            cache_path = draft.parent/(jid+'-'+str(index))/'social_copy.json'
            cache = host.load_json(cache_path) if host.metadata_exists(cache_path) else {}
            if not refresh and key in cache:
                return cache[key]
        # Provider calls must not block all project/draft mutations.
        result = generate_social_copy(context, platforms, body.vibe)
        with integration.lock:
            cache = host.load_json(cache_path) if host.metadata_exists(cache_path) else {}
            cache[key] = result
            cache = dict(list(cache.items())[-20:])
            host.save_json(cache_path, cache)
        return result
