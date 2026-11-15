"""One Cinema edit, start to finish: clean dialogue, story order, picture, score, mix, message, stamp."""
import logging
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from . import look, render, score, settings, speakers, speech, stamp
from .render import Overlay, Shot

LOG = logging.getLogger(__name__)
TAIL = settings.get('pacing.tail_seconds', .5)            # room after the last word
MESSAGE = settings.get('pacing.message_seconds', 3.4)     # the closing message, on its own, before the stamp


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


def camera_cuts(source, ffmpeg='ffmpeg', threshold=.16):
    """Where the source switches camera, found on small frames (podcast angles are dark and alike, so the bar is low)."""
    run = subprocess.run([ffmpeg, '-nostdin', '-i', str(source), '-vf', f"scale=160:-2,select='gt(scene,{threshold})',showinfo", '-an', '-f', 'null', '-'],
                         capture_output=True, text=True, timeout=1800)
    found = [float(t) for t in re.findall(r'pts_time:([\d.]+)', run.stderr)]
    return [t for n, t in enumerate(found) if not n or t-found[n-1] > .4]


def make(source, words, plan, out, cuts=(), find_broll=None, progress=None, ffmpeg='ffmpeg', use_matte=True, ratio='original', lines=1080):
    """Render `plan` over `source` to `out` (mp4). Deterministic: the same plan and footage give the same film,
    and no AI model is called. Returns a report with per-stage timings and the resolved timeline."""
    clock, timings = time.time(), {}
    def lap(name):
        nonlocal clock
        timings[name] = round(time.time()-clock, 1); clock = time.time()
    options = plan.settings
    ratio = options.ratio or ratio or 'original'
    progress = progress or (lambda a, s: None)
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    info = render.probe(source)
    look.configure(*render.size_for(info['width'], info['height'], ratio, lines))
    W, H = look.W, look.H
    wide = W > H

    # --- 1. clean dialogue, in story order
    progress(.04, 'Cleaning the dialogue…')
    samples = _audio(source, score.SR, ffmpeg)
    db = speech.energy(samples, score.SR)
    mono16 = samples.mean(1)[::3].astype(np.float32)
    question = next(((s.from_word, s.to_word) for s in plan.story if s.role == 'question'), None)
    answers = [(s.from_word, s.to_word) for s in plan.story if s.role in ('answer', 'payoff')]
    removed_fillers = speech.fillers(words) | speech.restarts(words)
    removed_others = speakers.interjections(words, mono16, 16000, question, answers) if question else set()
    drop = plan.dropped() | removed_fillers | removed_others
    edit = speech.cut(words, [(s.from_word, s.to_word) for s in plan.story], drop, db, duration=info['duration'])
    if not edit.pieces: raise ValueError('Nothing was left to play after cleaning the dialogue.')
    finder = find_broll or (lambda q: None)
    if hasattr(finder, 'prefetch'):   # fetch every b-roll clip while the dialogue is cut and framed
        finder.prefetch(([plan.opener.query or f'{plan.opener.word.lower()} aerial'] if plan.opener.style == 'mask' and plan.opener.word else [])
                        + [b.query for b in (plan.broll if options.broll else [])])
    hook_pieces = [p for p in edit.pieces if p.part == 0] if plan.story[0].role == 'hook' else []
    order = [i for p in edit.pieces if p.part > 0 or not hook_pieces for i in p.words]

    opener_path = None
    if plan.opener.style == 'mask' and plan.opener.word:
        opener_path = finder(plan.opener.query or f'{plan.opener.word.lower()} aerial')
    offset = render.VOICE_AT if opener_path else .2
    start = render.OPENER if opener_path else 0.
    speech_end = offset+edit.total+TAIL
    message = bool(plan.end_line.strip())
    main_end = speech_end+(MESSAGE if message else 0)
    # a word's time in the edit; a hook line plays twice, so look it up in its later, story place
    later = {}
    for p in edit.pieces:
        if p.part > 0 or not hook_pieces:
            for i in p.words: later.setdefault(i, p)
    def T(i, k=0):
        p = later.get(i)
        if p is None: return offset+edit.word_out[i][k]
        w = words[i]
        return offset+p.out+((max(p.a, w['s']) if k == 0 else min(p.b, w['e']))-p.a)
    in_story = lambda i: i in later or i in edit.word_out

    lap('dialogue')
    # --- 2. the speaker, framed: one shot per piece, split where the source cuts camera
    progress(.1, 'Framing every shot on the speaker…')
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
            s.cx = face[0] if not wide else .5
            s.face = render.face_in_output(face if not wide else (.5, face[1], face[2]), info['width'], info['height'])
            if wide: s.face = (face[0]*W, s.face[1]) if s.face else None
    zoom = 0
    for prev, s in zip([None]+shots[:-1], shots):
        if prev is not None and abs(prev.t1-s.t0) < .05 and abs(s.src-prev.src-(prev.t1-prev.t0)) > .04:
            zoom ^= 1    # a jump in the source behind a continuous edit: punch in or out to hide it
        s.zoom0 = render.PUNCH[zoom]; s.zoom1 = s.zoom0+.03

    lap('framing')
    # --- 3. designed moments
    overlays, events = [], []
    held = []        # windows that must stay on the speaker
    kw = {}
    for k in plan.keywords:
        if in_story(k.word): kw[k.word] = k.tone or look.tone_of(words[k.word]['w'])
    for m in plan.moments:
        if not in_story(m.word): continue
        tone = m.tone or kw.get(m.word) or look.tone_of(words[m.word]['w'])
        text = (m.text or words[m.word]['w']).strip('.,!?"\'').upper()
        t0 = T(m.word)
        if m.style in ('behind', 'outline'):
            shot = next((s for s in shots if s.t0 <= t0 < s.t1), None)
            face_y = shot.face[1] if shot and shot.face else H*.36
            overlays.append(Overlay(t0-.06, t0+1.65, m.style, {'text': text, 'tone': tone, 'y': max(H*.18, face_y-H*.14)}))
            held.append((t0-.3, t0+1.7))
            events.append((t0, 'moment', tone))
        elif m.style == 'glow':
            sent = _sentence(words, order, m.word)
            overlays.append(Overlay(t0-.1, max(t0+1.6, T(sent[-1], 1)+.2), 'glow', {'tone': tone}))
            held.append((t0-.3, t0+1.7))
        elif m.style == 'slam':
            overlays.append(Overlay(t0-.03, t0+.95, 'slam', {'text': text, 'tone': tone}))
            events.append((t0, 'slam', tone))
        elif m.style == 'serif':
            sent = _sentence(words, order, m.word)
            overlays.append(Overlay(T(sent[0])-.25, T(sent[-1], 1)+.6, 'quote', {'words': [(words[i]['w'], T(i), kw.get(i)) for i in sent]}))
    # the payoff: the music stops dead just before it, a sub hit lands on it, the words take the screen
    silence = None
    if plan.silence_before is not None and in_story(plan.silence_before):
        at = T(plan.silence_before)
        silence = (max(start+.5, at-.85), at)
        events.append((at, 'boom', 'calm'))
        if not any(o.kind == 'quote' for o in overlays):
            pos = order.index(plan.silence_before)
            sent = order[pos:]                      # the payoff runs to the last word
            if len(sent) > 18: sent = _sentence(words, order, plan.silence_before)
            if len(sent) <= 18:
                overlays.append(Overlay(T(sent[0])-.25, T(sent[-1], 1)+.6, 'quote', {'words': [(words[i]['w'], T(i), kw.get(i)) for i in sent]}))
    if hook_pieces:   # after the cold open, a flash and a hit, then the story starts
        end_hook = offset+hook_pieces[-1].out+hook_pieces[-1].length
        overlays.append(Overlay(end_hook-.05, end_hook+.07, 'flash'))
        events.append((end_hook, 'boom', 'calm'))

    # --- 4. b-roll: full screen, arriving just before its word, never over a giant-word moment
    progress(.18, 'Finding b-roll for what is said…')
    placed, used_paths = [], []
    for b in (plan.broll if options.broll else []):
        if not in_story(b.from_word): continue
        to = b.to_word if in_story(b.to_word) else b.from_word
        t0 = T(b.from_word)-.12
        t1 = max(t0+settings.get('broll.min_seconds', 1.5), min(t0+settings.get('broll.max_seconds', 3.4), T(to, 1)+.1))
        t1 = min(t1, speech_end)
        for a, z in sorted(held+placed):
            if a < t1 and t0 < z and z+1.1 <= t1: t0 = z+.02
        if t1-t0 < 1.0 or any(a < t1 and t0 < z for a, z in held+placed): continue
        quote = next((o for o in overlays if o.kind == 'quote' and o.t0 < t1 and t0 < o.t1), None)
        if quote: t1 = min(speech_end, max(t1, quote.t1))
        path = finder(b.query)
        if not path: continue
        src_len = render.probe(path)['duration']
        shot = Shot(t0, t1, 'broll', path, max(0, min(src_len*.2, src_len-(t1-t0)-.1)),
                    rate=1. if src_len > t1-t0+.3 else max(.4, (src_len-.2)/(t1-t0)),
                    zoom0=1., zoom1=1.07, grade='forest' if b.tone in ('life', 'water', 'hope', None) else plan.grade,
                    look='mono' if b.look == 'mono' else 'full', tone=b.tone or 'calm')
        shots = _overlay_shot(shots, shot)
        placed.append((t0, t1)); used_paths.append(path)
        events.append((t0+.12, 'broll', b.tone))
    # the closing message plays over the most beautiful b-roll we used (or the opener's footage)
    if message:
        still = opener_path or (used_paths[0] if used_paths else None)
        if still:
            length = render.probe(still)['duration']
            shots.append(Shot(speech_end, main_end, 'broll', still, max(0, length*.55-1), rate=max(.4, min(1., (length-.3)/MESSAGE)),
                              zoom0=1.04, zoom1=1.12, grade='forest', look='full'))
        else:
            last = max((s for s in shots if s.kind == 'aroll'), key=lambda s: s.t1)
            shots.append(Shot(speech_end, main_end, 'aroll', str(source), last.src+(last.t1-last.t0), zoom0=1.1, zoom1=1.16, grade='mono', look='mono', face=last.face, cx=last.cx))
        text = plan.end_line.strip()
        parts = text.split()
        marked = [n for n, w in enumerate(parts) if kw_tone(w)][:2]   # at most two coloured words in the message
        step = min(.32, 1.6/max(1, len(parts)))
        overlays.append(Overlay(speech_end+.15, main_end, 'message', {'words': [(w, speech_end+.35+n*step, kw_tone(w) if n in marked else None) for n, w in enumerate(parts)]}))
        events.append((speech_end+.3, 'boom', 'calm'))
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
    captions = render.Captions(words, edit, offset, kw, _placement(shots, wide)) if options.captions else None
    lap('broll')

    # --- 5. sound: voice on top, the score under it (silent before the payoff), no music under the stamp
    progress(.24, 'Composing the score…')
    total = main_end+(stamp.DURATION if options.stamp else 0)
    voice = np.zeros((int(total*score.SR), 2), np.float32)
    v = speech.render_voice(samples, score.SR, edit)
    i = int(offset*score.SR); voice[i:i+len(v)] = v[:len(voice)-i]
    hook_end = T(question[1], 1) if question and in_story(question[1]) else offset+3
    music = score.compose(main_end, {'silence': silence, 'end': main_end, 'hook_end': hook_end}, plan.mood)
    if not options.music: music = music*0
    if opener_path: events.append((.05, 'moment', 'water'))
    fx = score.sound_design(total, events)
    wav = out.with_suffix('.mix.wav')
    lufs, peak = score.mix(voice, music, fx, 0, wav, ffmpeg, music_under=settings.get('mix.music_under_voice_db', -17.)+options.music_db,
                           stamp=score.stamp_audio(stamp.DURATION) if options.stamp else None, stamp_at=main_end)
    lap('sound')

    # --- 6. picture
    progress(.3, 'Composing the picture…')
    matter = None
    if use_matte and any(o.kind in ('behind', 'outline', 'glow') for o in overlays):
        try:
            from .matte import Matter
            matter = Matter()
        except Exception:
            LOG.warning('person cut-outs unavailable; giant words go above the speaker', exc_info=True)
    if matter is None:
        for o in overlays:
            if o.kind in ('behind', 'outline'): o.kind = 'soft'
    composer = render.Composer(shots, overlays, captions, main_end, matter, ffmpeg, lambda a, s: progress(.3+.66*a, s), start=start)

    def all_frames():
        if opener_path:
            yield from render.opener_frames(plan.opener.word.upper(), opener_path, render.OPENER, ffmpeg)
        yield from composer.frames()
        last = composer.last if composer.last is not None else np.zeros((H, W, 3), np.uint8)
        if options.stamp: yield from stamp.frames(last)
    render.encode(all_frames(), wav, out, ffmpeg)
    wav.unlink(missing_ok=True)
    lap('picture')
    progress(1, 'Done')
    timeline = {
        'size': [W, H], 'fps': look.FPS, 'voice_starts': offset, 'speech_ends': round(speech_end, 3), 'ends': round(total, 3),
        'dialogue': [{'source_from': p.a, 'source_to': p.b, 'at': round(offset+p.out, 3), 'words': [p.words[0], p.words[-1]], 'part': p.part} for p in edit.pieces],
        'shots': [{'from': round(s.t0, 3), 'to': round(s.t1, 3), 'kind': s.kind, 'file': Path(s.path).name, 'source_from': round(s.src, 3), 'look': s.look} for s in shots],
        'overlays': [{'from': round(o.t0, 3), 'to': round(o.t1, 3), 'kind': o.kind, **({'text': o.data['text']} if 'text' in o.data else {})} for o in overlays],
        'music_silence': [round(x, 3) for x in silence] if silence else None,
    }
    broll_seconds = sum(z-a for a, z in placed)
    return {'seconds': round(total, 1), 'spoken_seconds': round(edit.total, 1), 'pieces': len(edit.pieces),
            'removed_fillers': len(removed_fillers & set(range(len(words)))), 'removed_interjections': len(removed_others),
            'broll': len(placed), 'broll_share': round(broll_seconds/max(1, edit.total)*100), 'moments': len(plan.moments),
            'lufs': lufs, 'peak': peak, 'cut_out': matter is not None, 'size': f'{W}x{H}', 'timings': timings, 'timeline': timeline}


def kw_tone(word):
    return look.tone_of(word, None)


def _placement(shots, wide):
    """Where the caption block sits at time t: in the empty side of the frame, away from the speaker's face."""
    W, H = look.W, look.H
    def place(t):
        shot = next((s for s in shots if s.t0 <= t < s.t1), None)
        if not wide:
            return 'center', W/2, H*.7, W*.84
        if shot is None or shot.kind != 'aroll' or not shot.face:
            return 'center', W/2, H*.74, W*.7
        if shot.face[0] > W*.5:
            return 'left', W*.065, H*.46, W*.4
        return 'right', W*.935, H*.46, W*.4
    return place


def _keep_moving(shots, longest=settings.get('pacing.longest_hold_seconds', 3.2)):
    """A visual change every 2-3 s: a long hold on the speaker becomes punch-in steps on the same take."""
    out = []
    for s in shots:
        if s.kind != 'aroll' or s.t1-s.t0 <= longest+.6:
            out.append(s); continue
        steps = int((s.t1-s.t0)//2.6)
        length = (s.t1-s.t0)/steps
        zoom = s.zoom0
        for n in range(steps):
            part = Shot(**{**s.__dict__})
            part.t0 = s.t0+n*length
            part.t1 = s.t1 if n == steps-1 else s.t0+(n+1)*length
            part.src = s.src+(part.t0-s.t0)*s.rate
            part.zoom0 = zoom; part.zoom1 = zoom+.03
            zoom = 1.12 if zoom < 1.06 else 1.0
            out.append(part)
    return out


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
