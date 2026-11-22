"""Everything measured from the clip once and reused by every revision: the clip's audio, word
times (Deepgram), shot boundaries and labelled contact sheets for OpenAI to watch."""
import json
import math
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import tools

RUN = dict(capture_output=True, text=True)


def probe(path):
    data = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json', str(path)],
                                     **RUN, timeout=60, check=True).stdout)
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    return {'duration': float(data['format']['duration']), 'width': video and video['width'], 'height': video and video['height'],
            'has_audio': any(s['codec_type'] == 'audio' for s in data['streams'])}


def _energy(path, folder):
    mono = folder/'voice16.wav'
    subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-y', '-i', str(path), '-ac', '1', '-ar', '16000', str(mono)], check=True, timeout=300, **RUN)
    with wave.open(str(mono)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2')/32768
    hop = 160
    power = np.convolve(x**2, np.ones(320)/320, 'same')[::hop]
    return mono, x, 10*np.log10(power+1e-12)


def _transcribe(mono, x, db, folder):
    """Deepgram word times, checked against the voice's own energy. None when Deepgram is unavailable."""
    from backend.cascade_stt import TranscriptionError, transcribe_words
    try:
        words = transcribe_words(mono)
    except TranscriptionError:
        return None
    # Snap each start to the nearest rise in energy, keep order, end each word where the next begins or the voice stops.
    end_of_audio = len(db)/100
    last = -1.
    for word in words:
        lo, hi = max(0, int((word['s']-.2)*100)), int((word['s']+.08)*100)
        if hi > lo+2:
            word['s'] = (lo+int(np.argmax(np.diff(db[lo:hi])))+1)/100
        word['s'] = max(word['s'], last+.05); last = word['s']
    for word, following in zip(words, [*words[1:], None]):
        limit = following['s'] if following else end_of_audio
        word['e'] = round(min(limit, max(word['e'], word['s']+.08)), 3)
        tail = int(word['e']*100)
        while tail > int(word['s']*100)+5 and tail < len(db) and db[tail] < -42: tail -= 1  # do not hold silence as a word
        word['e'] = round(max(tail/100+.04, word['s']+.08), 3); word['s'] = round(word['s'], 3)
    return words


def _from_cues(cues):
    """Without Deepgram: spread the existing transcript's words through each cue."""
    words = []
    for cue in cues:
        parts = cue['text'].split()
        if not parts: continue
        step = (cue['end']-cue['start'])/len(parts)
        words += [{'w': w, 's': round(cue['start']+i*step, 3), 'e': round(cue['start']+(i+1)*step, 3)} for i, w in enumerate(parts)]
    return words


MIN_WORDS = 6


def motion(source, ffmpeg=None):
    """How much moves in each second of the clip, 0 (still) to 9 (the most motion in this clip)."""
    w, h, rate = 64, 36, 4
    raw = subprocess.run([ffmpeg or tools.ffmpeg(), '-nostdin', '-v', 'error', '-i', str(source), '-vf', f'fps={rate},scale={w}:{h},format=gray',
                          '-an', '-f', 'rawvideo', '-'], capture_output=True, timeout=1800).stdout
    frames = np.frombuffer(raw, np.uint8)[:len(raw)//(w*h)*w*h].reshape(-1, h, w).astype(np.float32)
    if len(frames) < 2: return [0]*max(1, len(frames)//rate)
    diff = np.abs(np.diff(frames, axis=0)).mean((1, 2))
    diff = np.concatenate([[diff[0]], diff])
    per_second = [float(diff[i:i+rate].mean()) for i in range(0, len(diff), rate)]
    top = max(per_second) or 1.
    return [int(round(9*v/top)) for v in per_second]


def _cuts(source):
    run = subprocess.run(['ffmpeg', '-nostdin', '-i', str(source), '-vf', "scale=320:-2,select='gt(scene,0.3)',showinfo", '-f', 'null', '-'], timeout=1800, **RUN)
    found = [float(t) for t in re.findall(r'pts_time:([\d.]+)', run.stderr)]
    return [t for n, t in enumerate(found) if not n or t-found[n-1] > .25]  # a burst of "cuts" is a dissolve or a flash


def _sheets(source, duration, folder):
    """Labelled contact sheets of the whole clip: each cell shows its source second, so Claude can name shots."""
    every = 1 if duration <= 48 else max(2, math.ceil(duration/140))
    drawn = f"fps=1/{every},scale=320:-2,drawtext=text='%{{eif\\:n*{every}\\:d}}s':x=6:y=6:fontsize=24:fontcolor=white:box=1:boxcolor=black,tile=8x6"
    subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-y', '-i', str(source), '-vf', drawn, '-q:v', '4', str(folder/'sheet%02d.jpg')], check=True, timeout=1800, **RUN)
    return every


def prepare(source, cues, folder, progress, speech_optional=False):
    """Returns the measurements; cached in `folder` for the life of the clip. Words come from Deepgram.
    `speech_optional=True` (the Cinema engine) accepts a clip with no speech or no sound: `words` is then
    empty and `motion` says how much moves in each second, for a visual edit."""
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    done = folder/'prep.json'
    stat = Path(source).stat()
    stamp = [stat.st_size, stat.st_mtime_ns]
    if done.is_file():
        saved = json.loads(done.read_text())
        if saved.get('stamp') == stamp: return saved
    media = probe(source)
    if not media['width']: raise ValueError('This clip has no video.')
    if not media['has_audio'] and not speech_optional: raise ValueError('This clip has no sound, and this edit is built around what is said.')
    db = None
    if not media['has_audio']:
        words = []
    else:
        voice = folder/'mix.wav'
        subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-y', '-i', str(source), '-vn', '-ac', '2', '-ar', '44100', str(voice)], check=True, timeout=600, **RUN)
    if media['has_audio']:
        progress(.2, 'Transcribing every word…')
        mono, x, db = _energy(voice, folder)
        words = _transcribe(mono, x, db, folder)
        if words is None: words = _from_cues(cues)
    if speech_optional and len(words) < MIN_WORDS: words = []   # a stray word or two is not a talk to edit around
    if not words and not speech_optional: raise ValueError('I could not find any speech in this clip to edit around.')
    progress(.28, 'Finding the shots…')
    cuts = _cuts(source)
    every = _sheets(source, media['duration'], folder)
    if db is not None: np.save(folder/'energy.npy', db.astype('float32'))
    saved = {**media, 'stamp': stamp, 'voice': Path(voice).name if media['has_audio'] else None, 'words': [{**w, 'i': i} for i, w in enumerate(words)],
             'cuts': cuts, 'sheet_every': every, 'sheets': sorted(p.name for p in folder.glob('sheet*.jpg')),
             'motion': motion(source) if not words else []}
    done.write_text(json.dumps(saved))
    return saved
