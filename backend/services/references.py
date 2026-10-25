"""Parse explicit numbered examples and resolve them within an owned session."""
import json
import re
from fastapi import HTTPException
from backend import integration as store
from backend.services.sessions import require_session, job_session

MAX_REFERENCES = 6
# A marker is required; ordinary requested counts are not clip references.
_REFERENCE = re.compile(r'(?:\bclips?\b\s*|\bselected\b\s*|(?<!\w)#\s*)(\d+(?:(?:\s*,\s*(?:(?:and|&)\s*)?|\s+(?:and|&)\s*)#?\s*\d+)*)', re.I)


def parse_reference_numbers(prompt):
    return sorted({int(n) for match in _REFERENCE.finditer(prompt) for n in re.findall(r'\d+', match.group(1))})


def build_clip_context(job_id, clip_index):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id) or type(clip_index) is not int or clip_index < 0:
        raise HTTPException(404, 'Clip not found.')
    folder = store.host.JOBS_DIR / job_id
    if not (folder / 'results.json').is_file():
        raise HTTPException(409, 'Clip is not ready.')
    owner = json.loads((folder / 'owner.json').read_text(encoding='utf-8'))
    clips = json.loads((folder / 'results.json').read_text(encoding='utf-8')).get('clips', [])
    if clip_index >= len(clips):
        raise HTTPException(404, 'Clip not found.')
    clip = clips[clip_index]
    context = {'clip_id': f'{job_id}:{clip_index}', 'job_id': job_id, 'clip_index': clip_index,
               'start': clip['start'], 'end': clip['end'], 'title': clip.get('title', ''),
               'prompt': owner.get('prompt', ''), 'description': clip.get('explanation', '')}
    captions = folder / f'clip_{clip_index + 1}.vtt'
    if captions.is_file():
        context['captions'] = captions.read_text(encoding='utf-8-sig')[:4000]
    return context


def resolve_references(project, session_id, numbers):
    numbers = sorted(set(numbers))
    if len(numbers) > MAX_REFERENCES:
        raise HTTPException(400, 'Choose at most 6 reference clips.')
    session = require_session(project, session_id)
    selections = {s['number']: s for s in session['selections']}
    result = []
    for number in numbers:
        if number not in selections:
            raise HTTPException(400, f'There is no Selected {number} in this session')
        selection = selections[number]
        owner, _ = store.selected_clip(project['id'], store.ClipInput(
            job_id=selection['job_id'], clip_index=selection['clip_index']), project['user_id'])
        if job_session(project, owner) != session['id']:
            raise HTTPException(400, 'Reference clip must belong to this session.')
        result.append({'number': number, **build_clip_context(selection['job_id'], selection['clip_index'])})
    return result
