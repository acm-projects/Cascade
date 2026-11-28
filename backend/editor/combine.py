"""Multi-clip editing: join clips picked in AI Studio (say clip 1 and clip 3) into one clip and edit that.

POST /api/projects/{pid}/editor/combine  {"clips": [{"job_id": ..., "clip_index": 0}, ...], "title": optional}

The joined video becomes a one-clip job (kind "combined"), shaped exactly like an uploaded clip (see own_clip.py),
so every Editor feature (drafts, captions, B-roll, AI Editor, export) works on it unchanged. Each part is the clip's
own video (the same file the Editor plays for it), scaled to the first part's frame size, and the captions are
carried over with their times shifted. The result goes first in the Editor's clip list, so the Editor opens it.
"""
import hashlib
import logging
import re
import shutil
import subprocess
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from backend.core import config, jobs as job_service, storage as storage_service
from backend.services import projects_store

MAX_PARTS = 30
MAX_SECONDS = 15*60
FADE = .012          # seconds of fade on the sound at each join, so the seams don't click


class Part(BaseModel):
    job_id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    clip_index: int = Field(ge=0, le=999)


class CombineInput(BaseModel):
    clips: list[Part] = Field(min_length=2, max_length=MAX_PARTS)
    title: str | None = Field(default=None, max_length=120)


# ---------- captions ----------

TIME = re.compile(r'(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})')


def _seconds(text):
    m = TIME.fullmatch(text.strip())
    if not m: raise ValueError(text)
    h, mi, s, ms = m.groups()
    return int(h or 0)*3600+int(mi)*60+int(s)+int(ms)/1000


def _stamp(t):
    t = max(0., t)
    ms = int(round(t*1000))
    return f'{ms//3600000:02d}:{ms//60000 % 60:02d}:{ms//1000 % 60:02d}.{ms % 1000:03d}'


def cues(vtt_text):
    """[(start, end, text)] from a WebVTT file (clip-relative times)."""
    out = []
    for block in re.split(r'\n\s*\n', (vtt_text or '').replace('\r\n', '\n')):
        lines = [line for line in block.strip().split('\n') if line.strip()]
        timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing is None: continue
        a, _, rest = lines[timing].partition('-->')
        try:
            start, end = _seconds(a), _seconds(rest.split()[0])
        except (ValueError, IndexError):
            continue
        text = '\n'.join(lines[timing+1:]).strip()
        if text and end > start: out.append((start, end, text))
    return out


def merged_captions(parts):
    """One WebVTT for the joined clip. parts: [(vtt_text, duration)] in order."""
    lines, offset = ['WEBVTT', ''], 0.
    for text, duration in parts:
        for start, end, words in cues(text):
            start, end = min(start, duration), min(end, duration)
            if end > start: lines += [f'{_stamp(offset+start)} --> {_stamp(offset+end)}', words, '']
        offset += duration
    return '\n'.join(lines)+'\n'


# ---------- video ----------

def _even(n):
    return max(2, int(n)//2*2)


def join_command(parts, out, width, height, fps=30):
    """ffmpeg command joining [(source, start, end, has_audio)] into one H.264/AAC mp4 of width x height."""
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y']
    for source, start, end, _ in parts:
        command += ['-ss', f'{start:.3f}', '-t', f'{end-start:.3f}', '-i', str(source)]
    graph, labels = [], ''
    for n, (_, start, end, has_audio) in enumerate(parts):
        d = end-start
        graph.append(f'[{n}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,'
                     f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p,'
                     f'trim=duration={d:.3f},setpts=PTS-STARTPTS[v{n}]')
        sound = (f'[{n}:a:0]aresample=48000,aformat=channel_layouts=stereo,' if has_audio
                 else f'anullsrc=r=48000:cl=stereo,')
        graph.append(f'{sound}atrim=duration={d:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={d:.3f},'
                     f'afade=t=in:d={FADE},afade=t=out:st={max(0., d-FADE):.3f}:d={FADE}[a{n}]')
        labels += f'[v{n}][a{n}]'
    graph.append(f'{labels}concat=n={len(parts)}:v=1:a=1[v][a]')
    return command+['-filter_complex', ';'.join(graph), '-map', '[v]', '-map', '[a]',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(out)]


# ---------- route ----------

def _part(pid, user, ref, stack):
    """One picked clip: its video file (kept available until `stack` closes), length, title and captions."""
    from backend.media import probe_media
    from .storage import media
    owner, clip = projects_store.selected_clip(pid, ref, user)
    if not clip.get('has_video', True) or clip.get('media_kind', 'video') != 'video':
        raise HTTPException(400, f'Clip {ref.clip_index+1} has no video, so it cannot be combined.')
    path = stack.enter_context(media(ref.job_id, clip))
    info = probe_media(path)
    if not info['has_video']: raise HTTPException(400, f'Clip {ref.clip_index+1} has no video, so it cannot be combined.')
    captions = ''
    try:
        with media(ref.job_id, clip, captions=True) as vtt:
            captions = vtt.read_text(encoding='utf-8-sig')
    except (HTTPException, OSError, UnicodeDecodeError):
        pass                                   # no captions for this part: the rest still carry theirs
    return {'path': path, 'duration': info['duration'], 'info': info, 'title': clip.get('title') or f'Clip {ref.clip_index+1}',
            'captions': captions, 'start': float(clip.get('start', 0)), 'end': float(clip.get('end', 0))}


def timeline(parts):
    """[{'title', 'from', 'to'}]: each picked clip's place in the joined video, in order."""
    out, at = [], 0.
    for p in parts:
        out.append({'title': p['title'][:120], 'from': round(at, 2), 'to': round(at+p['duration'], 2)})
        at += p['duration']
    return out


def default_title(titles):
    title = ' + '.join(t.strip() for t in titles if t.strip())
    return title if len(title) <= 120 else f'{len(titles)} clips combined'


def combine_clips(pid: str, body: CombineInput, request: Request):
    user = request.state.user_id
    projects_store.require_project(pid, user)
    if shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None:
        raise HTTPException(503, 'FFmpeg and ffprobe must be installed.')
    seen, refs = set(), []
    for ref in body.clips:
        key = (ref.job_id, ref.clip_index)
        if key not in seen: seen.add(key); refs.append(ref)
    if len(refs) < 2: raise HTTPException(400, 'Pick at least two different clips to combine.')
    from backend import demo
    fast = demo.combine_parts(pid, user, refs)
    if fast: return _combine(pid, user, body, refs, fast)
    with ExitStack() as stack:
        parts = [_part(pid, user, ref, stack) for ref in refs]
        return _combine(pid, user, body, refs, parts)


def _combine(pid, user, body, refs, parts):
    from backend.media import probe_media
    total = sum(p['duration'] for p in parts)
    if total > MAX_SECONDS: raise HTTPException(400, 'The combined clip would be longer than 15 minutes. Pick fewer clips.')
    first = parts[0]['info']
    width, height = _even(first.get('width') or 1080), _even(first.get('height') or 1920)

    storage = {'folder': config.DEFAULT_FOLDER, 'source': 'local'}
    if not storage_service.uses_local_storage():
        try:
            storage = storage_service.resolve_storage_folder(user)
        except Exception:
            logging.getLogger(__name__).warning('Could not resolve the storage folder for a combined clip; using the default.')

    job_id = uuid4().hex
    folder = job_service.JOBS_DIR/job_id
    folder.mkdir(parents=True)
    try:
        joined = folder/'combined.mp4'
        from backend import demo
        demo_edit = demo.is_demo_combine(refs)
        if demo_edit:   # demo mode: the picked hike clips, joined in the edit's order
            shutil.copyfile(demo.combined_file(), joined)
            run = subprocess.CompletedProcess([], 0, '', '')
        else:
            command = join_command([(p['path'], 0., p['duration'], p['info']['has_audio']) for p in parts], joined, width, height)
            run = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if run.returncode or not joined.is_file():
            logging.getLogger(__name__).error('Combining clips failed: %s', run.stderr[-1500:])
            raise HTTPException(500, 'Could not combine the clips. Try again, or pick different clips.')
        source = folder/'source.video'
        joined.replace(source)
        info = probe_media(source)
        fingerprint = hashlib.sha256()
        with source.open('rb') as f:
            while chunk := f.read(1024*1024): fingerprint.update(chunk)
        title = (body.title or '').strip() or ('Hike with Cascade' if demo_edit else default_title([p['title'] for p in parts]))
        owner = {'user_id': user, 'project_id': pid, 'kind': 'combined', 'prompt': '', 'source_name': f'{title}.mp4',
                 'media_kind': 'video', 'video_sha256': fingerprint.hexdigest(), 'requested_clip_count': 1,
                 'history_id': job_id, 'source_job': job_id, 'created_at': time.time(),
                 'combined_from': [{**r.model_dump(), 'start': p['start'], 'end': p['end']} for r, p in zip(refs, parts)],
                 # where each picked clip sits in the joined video, with its Studio title, so the AI Editor knows which is which
                 'parts': demo.combined_parts() if demo_edit else timeline(parts), **({'demo': True} if demo_edit else {}),
                 'user_folder': storage['folder'], 'folder_source': storage['source'], **info}
        job_service.save_json(folder/'owner.json', owner)
        shutil.copyfile(source, folder/'clip_1.mp4')
        (folder/'clip_1.vtt').write_text(merged_captions([(p['captions'], p['duration']) for p in parts]), encoding='utf-8')
        numbers = ', '.join(f'clip {r.clip_index+1}' for r in refs)
        clip = {'clip_id': f'{job_id}:0', 'start': 0.0, 'end': info['duration'], 'title': title,
                'explanation': f'Combined from {numbers}', 'media_kind': 'video', 'has_video': True,
                'clip_url': f'/clips/{job_id}/clip_1.mp4', 'captions_url': f'/clips/{job_id}/clip_1.vtt'}
        job_service.save_json(folder/'results.json', {'clips': [clip], 'requested_clip_count': 1})
        from backend.services import project_thumbnails
        project_thumbnails.save(job_id, [clip])
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    # First in the Editor's clip list, so the Editor opens the combined edit
    from backend import studio
    with projects_store.lock:
        project = studio.ensure(pid, user)
        ref = {'job_id': job_id, 'clip_index': 0}
        studio.set_selection(project['studio'], [ref, *project['studio'].get('editor_clips', [])])
        project['editor_selection'] = ref
        studio.save(project, user)
    if not storage_service.uses_local_storage() and not demo_edit:   # (demo: no 70 MB upload competing with the demo)
        from .own_clip import _back_up
        threading.Thread(target=_back_up, args=(folder, job_id), daemon=True).start()
    return {**ref, 'title': title, 'duration': info['duration'], 'parts': len(parts)}
