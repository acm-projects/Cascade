"""Read finished source windows from only the current, owner-verified session."""
import math


def session_clip_windows(project, sid, host, integration, user_id):
    session = next((s for s in project.get('studio', {}).get('sessions', []) if s['id'] == sid), None)
    if session is None:
        return []
    windows = []
    for jid in reversed(session['job_ids']):
        owner = integration.owner_for_job(project['id'], jid, user_id)
        if owner.get('kind', 'generation') != 'generation':
            continue
        path = host.JOBS_DIR / jid / 'results.json'
        if not host.metadata_exists(path):
            continue
        result = host.load_json(path)
        if result.get('state', 'done') != 'done':
            continue
        for clip in reversed(result.get('clips', [])):
            try:
                start, end = float(clip['start']), float(clip['end'])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(start) and math.isfinite(end) and 0 <= start < end:
                windows.append([start, end])
                if len(windows) == 60:
                    return windows
    return windows
