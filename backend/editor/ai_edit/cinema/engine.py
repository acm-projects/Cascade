"""One Cinema edit, start to finish: clean dialogue, picture, score, mix, stamp."""
import logging
import subprocess
from pathlib import Path

import numpy as np

from . import look, render, score, speakers, speech, stamp
from .render import Overlay, Shot

LOG = logging.getLogger(__name__)
TAIL = .45   # room after the last word before the stamp


def _audio(path, sr, ffmpeg='ffmpeg'):
    raw = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-ac', '2', '-ar', str(sr), '-f', 'f32le', '-'],
                         capture_output=True, timeout=900).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def _sentence(words, order, i):
    """The kept words of the sentence that holds word i."""
    pos = order.index(i)
    a = pos
    while a > 0 and not words[order[a-1]]['w'].rstrip().endswith(('.', '?', '!')): a -= 1
    b = pos
    while b < len(order)-1 and not words[order[b]]['w'].rstrip().endswith(('.', '?', '!')): b += 1
    return order[a:b+1]


def make(source, words, plan, out, cuts=(), find_broll=None, progress=None, ffmpeg='ffmpeg', use_matte=True):
    """Render `plan` over `source` to `out` (mp4). Returns a report dict."""
    progress = progress or (lambda a, s: None)
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    info = render.probe(source)
    progress(.05, 'Cleaning the dialogue…')
    samples = _audio(source, score.SR, ffmpeg)
    db = speech.energy(samples, score.SR)
    mono16 = samples.mean(1)[::3].astype(np.float32)
    question = next(((s.from_word, s.to_word) for s in plan.story if s.role in ('question', 'hook')), None)
    answers = [(s.from_word, s.to_word) for s in plan.story if s.role in ('answer', 'payoff')]
    removed_fillers = speech.fillers(words)
    removed_others = speakers.interjections(words, mono16, 16000, question, answers) if question else set()
    drop = plan.dropped() | removed_fillers | removed_others
    edit = speech.cut(words, [(s.from_word, s.to_word) for s in plan.story], drop, db, duration=info['duration'])
    if not edit.pieces: raise ValueError('Nothing was left to play after cleaning the dialogue.')
    order = edit.order
    finder = find_broll or (lambda q: None)

    opener_path = None
    if plan.opener.style == 'mask' and plan.opener.word:
        opener_path = finder(plan.opener.query or f'{plan.opener.word.lower()} aerial')
    offset = render.VOICE_AT if opener_path else .2
    start = render.OPENER if opener_path else 0.
    main_end = offset+edit.total+TAIL
    T = lambda i, k=0: offset+edit.word_out[i][k]

    # --- A-roll shots: one per dialogue piece, split again where the source itself cuts camera
    progress(.12, 'Framing every shot on the speaker…')
    cuts = sorted(set(round(c, 2) for c in list(cuts)+camera_cuts(source, ffmpeg)))
    shots = []
    for p in edit.pieces:
        bounds = [p.a]+[c for c in cuts if p.a+.05 < c < p.b-.05]+[p.b]
        for a, b in zip(bounds, bounds[1:]):
            shots.append(Shot(offset+p.out+a-p.a, offset+p.out+b-p.a, 'aroll', str(source), a, grade=plan.grade))
    cache = {}
    for s in shots:
        key = round(s.src+(s.t1-s.t0)/2, 1)
        face = cache.get(key) or render.find_face(source, key, ffmpeg)
        cache[key] = face
        if face:
            s.cx = face[0]
            s.face = (look.W/2, face[1]*look.H)
    zoom = 0
    for prev, s in zip([None]+shots[:-1], shots):
        if prev is not None and abs(prev.t1-s.t0) < .05 and abs(s.src-prev.src-(prev.t1-prev.t0)) > .04:
            zoom ^= 1    # a jump in the source behind a continuous edit: punch in or out to hide it
        s.zoom0 = render.PUNCH[zoom]
        s.zoom1 = s.zoom0+.035
    # --- designed moments
    overlays, events = [], []
    behind_windows = []
    moment_words = {m.word for m in plan.moments}
    kw = {}
    for k in plan.keywords:
        if k.word in edit.word_out: kw[k.word] = k.tone or look.tone_of(words[k.word]['w'])
    serif_words = set()
    for m in plan.moments:
        if m.word not in edit.word_out: continue
        tone = m.tone or kw.get(m.word) or look.tone_of(words[m.word]['w'])
        text = (m.text or words[m.word]['w']).strip('.,!?"\'').upper()
        t0 = T(m.word)
        if m.style in ('behind', 'outline'):
            # the giant word sits just above the face so the head covers its lower half
            shot = next((s for s in shots if s.t0 <= t0 < s.t1), None)
            face_y = shot.face[1] if shot and shot.face else look.H*.36
            overlays.append(Overlay(t0-.06, t0+1.65, m.style, {'text': text, 'tone': tone, 'y': max(look.H*.16, face_y-look.H*.12)}))
            behind_windows.append((t0-.3, t0+1.7))
            events.append((t0, 'moment', tone))
        elif m.style == 'glow':
            sent = _sentence(words, order, m.word)
            overlays.append(Overlay(t0-.1, max(t0+1.6, T(sent[-1], 1)+.2), 'glow', {'tone': tone}))
            behind_windows.append((t0-.3, t0+1.7))
        elif m.style == 'slam':
            overlays.append(Overlay(t0-.03, t0+.95, 'slam', {'text': text, 'tone': tone}))
            events.append((t0, 'slam', tone))
        elif m.style == 'serif':
            sent = _sentence(words, order, m.word)
            serif_words.update(sent)
            items = [(words[i]['w'], T(i), kw.get(i)) for i in sent]
            overlays.append(Overlay(T(sent[0])-.25, T(sent[-1], 1)+.7, 'serif', {'words': items}))
    # the payoff: music stops just before it, a sub hit lands on it
    silence = None
    if plan.silence_before is not None and plan.silence_before in edit.word_out:
        at = T(plan.silence_before)
        silence = (max(start+.5, at-.85), at)
        events.append((at, 'boom', 'calm'))
        if not any(o.kind == 'serif' for o in overlays):
            sent = _sentence(words, order, plan.silence_before)
            if len(sent) <= 14:
                serif_words.update(sent)
                overlays.append(Overlay(T(sent[0])-.25, T(sent[-1], 1)+.7, 'serif', {'words': [(words[i]['w'], T(i), kw.get(i)) for i in sent]}))
    # --- b-roll: arrives just before its word, never over a giant-word moment
    progress(.2, 'Finding b-roll for what is said…')
    placed = []
    for b in plan.broll:
        if b.from_word not in edit.word_out: continue
        to = b.to_word if b.to_word in edit.word_out else b.from_word
        t0 = T(b.from_word)-.12
        t1 = max(t0+1.3, min(t0+3.2, T(to, 1)+.08))
        t1 = min(t1, main_end)
        # arrive after a giant-word moment instead of being dropped, if the line is still going
        for a, z in sorted(behind_windows+placed):
            if a < t1 and t0 < z and z+1.0 <= t1: t0 = z+.02
        if any(a < t1 and t0 < z for a, z in behind_windows+placed): continue
        # under the payoff's serif words the picture holds on this shot to the end of the line
        serif = next((o for o in overlays if o.kind == 'serif' and o.t0 < t1 and t0 < o.t1), None)
        if serif: t1 = min(main_end, max(t1, serif.t1))
        if any(o.kind == 'serif' and o.t0 < t1 and t0 < o.t1 for o in overlays) and b.look == 'full': b.look = 'mono'
        path = finder(b.query)
        if not path: continue
        src_len = render.probe(path)['duration']
        shot = Shot(t0, t1, 'broll', path, max(0, min(src_len*.25, src_len-(t1-t0)-.1)), rate=1. if src_len > t1-t0+.3 else max(.4, (src_len-.2)/(t1-t0)),
                    zoom0=1., zoom1=1.06, grade='forest' if (b.tone in ('life', 'water', 'hope', None)) else plan.grade, look=b.look, tone=b.tone or 'calm')
        shots = _overlay_shot(shots, shot)
        placed.append((t0, t1))
        events.append((t0+.12, 'broll', b.tone))
        overlays.append(Overlay(t1-.04, t1+.06, 'flash'))
    shots.sort(key=lambda s: s.t0)
    shots = [s for s in shots if s.t1-s.t0 > 1/look.FPS]
    shots = _keep_moving(shots)
    if start > 0:
        first = [s for s in shots if s.t1 > start]
        if first and first[0].t0 < start:
            first[0].src += (start-first[0].t0)*first[0].rate
            first[0].t0 = start
        shots = first
    if plan.title:
        overlays.append(Overlay(start+.15, start+2.2, 'title', {'text': plan.title}))
    hidden = set()
    captions = render.Captions(words, edit, offset, kw, hidden)

    # --- sound
    progress(.28, 'Composing the score…')
    total = main_end+stamp.DURATION
    voice = np.zeros((int(total*score.SR), 2), np.float32)
    v = speech.render_voice(samples, score.SR, edit)
    i = int(offset*score.SR); voice[i:i+len(v)] = v[:len(voice)-i]
    music = score.compose(main_end, {'silence': silence, 'end': main_end, 'hook_end': T(question[1], 1) if question and question[1] in edit.word_out else offset+3}, plan.mood)
    if opener_path: events.append((.05, 'moment', 'water'))
    fx = score.sound_design(total, events)
    wav = out.with_suffix('.mix.wav')
    lufs, peak = score.mix(voice, music, fx, 0, wav, ffmpeg, music_under=-17., stamp=score.stamp_audio(stamp.DURATION), stamp_at=main_end)

    # --- picture
    progress(.32, 'Composing the picture…')
    matter = None
    if use_matte and any(o.kind in ('behind', 'outline', 'glow') for o in overlays):
        try:
            from .matte import Matter
            matter = Matter()
        except Exception:
            LOG.warning('person cut-outs unavailable; giant words go in front', exc_info=True)
    if matter is None:   # without a cut-out the giant word sits above the speaker's head instead of behind it
        for o in overlays:
            if o.kind in ('behind', 'outline'): o.kind = 'slam_soft'
    composer = render.Composer(shots, overlays, captions, main_end, matter, ffmpeg, lambda a, s: progress(.32+.6*a, s), start=start)

    def all_frames():
        if opener_path:
            yield from render.opener_frames(plan.opener.word.upper(), opener_path, render.OPENER, ffmpeg)
        last = None
        for frame in composer.frames():
            last = frame
            yield frame
        yield from stamp.frames(last if last is not None else np.zeros((look.H, look.W, 3), np.uint8))
    render.encode(all_frames(), wav, out, ffmpeg)
    wav.unlink(missing_ok=True)
    progress(1, 'Done')
    return {'seconds': round(total, 1), 'spoken_seconds': round(edit.total, 1), 'pieces': len(edit.pieces),
            'removed_fillers': len(removed_fillers & set(range(len(words)))), 'removed_interjections': len(removed_others),
            'broll': len(placed), 'moments': len(plan.moments), 'lufs': lufs, 'peak': peak,
            'cut_out': matter is not None}


def _keep_moving(shots, longest=3.0):
    """A visual change every 2-3 s: a long hold on the speaker becomes punch-in steps on the same take."""
    out = []
    for s in shots:
        if s.kind != 'aroll' or s.t1-s.t0 <= longest+.6:
            out.append(s); continue
        steps = int((s.t1-s.t0)//2.4)
        length = (s.t1-s.t0)/steps
        zoom = s.zoom0
        for n in range(steps):
            part = Shot(**{**s.__dict__})
            part.t0 = s.t0+n*length
            part.t1 = s.t1 if n == steps-1 else s.t0+(n+1)*length
            part.src = s.src+(part.t0-s.t0)*s.rate
            part.zoom0 = zoom; part.zoom1 = zoom+.03
            zoom = 1.13 if zoom < 1.06 else 1.0
            out.append(part)
    return out


def camera_cuts(source, ffmpeg='ffmpeg', threshold=.16):
    """Where the source switches camera, found on small frames (podcast angles are dark and alike, so the bar is low)."""
    import re
    run = subprocess.run([ffmpeg, '-nostdin', '-i', str(source), '-vf', f"scale=160:-2,select='gt(scene,{threshold})',showinfo", '-an', '-f', 'null', '-'],
                         capture_output=True, text=True, timeout=1800)
    found = [float(t) for t in re.findall(r'pts_time:([\d.]+)', run.stderr)]
    return [t for n, t in enumerate(found) if not n or t-found[n-1] > .4]


def _overlay_shot(shots, new):
    out = []
    for s in shots:
        if s.t1 <= new.t0 or s.t0 >= new.t1:
            out.append(s); continue
        if s.t0 < new.t0:
            left = Shot(**{**s.__dict__}); left.t1 = new.t0; out.append(left)
        if s.t1 > new.t1:
            right = Shot(**{**s.__dict__})
            right.src = s.src+(new.t1-s.t0)*s.rate
            right.t0 = new.t1
            out.append(right)
    out.append(new)
    return sorted(out, key=lambda s: s.t0)
