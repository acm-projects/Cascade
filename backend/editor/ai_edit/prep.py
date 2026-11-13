"""Everything measured from the clip once and reused by every revision: the isolated voice, word
times, shot boundaries and labelled contact sheets for Claude to watch."""
import json
import math
import re
import shutil
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


def _voice(source, folder):
    """The dialogue alone, so composed music never clashes with a score already in the clip. Falls back to the mix."""
    mix = folder/'mix.wav'
    subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-y', '-i', str(source), '-vn', '-ac', '2', '-ar', '44100', str(mix)], check=True, timeout=600, **RUN)
    python = tools.demucs()
    if not python: return mix, False
    import platform
    stem = folder/'sep'/'htdemucs'/'mix'/'vocals.wav'
    run = None
    if platform.system() == 'Darwin' and platform.machine() == 'arm64':  # Apple GPU only exists on Apple silicon Macs
        run = subprocess.run([python, '-m', 'demucs', '--two-stems=vocals', '-d', 'mps', '-o', str(folder/'sep'), str(mix)], timeout=1800, cwd=folder, **RUN)
    if run is None or run.returncode or not stem.is_file():
        run = subprocess.run([python, '-m', 'demucs', '--two-stems=vocals', '-d', 'cpu', '-o', str(folder/'sep'), str(mix)], timeout=3600, cwd=folder, **RUN)
    if not stem.is_file(): return mix, False
    final = folder/'voice.wav'
    shutil.move(stem, final)
    shutil.rmtree(folder/'sep', ignore_errors=True)
    return final, True


def _energy(path, folder):
    mono = folder/'voice16.wav'
    subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-y', '-i', str(path), '-ac', '1', '-ar', '16000', str(mono)], check=True, timeout=300, **RUN)
    with wave.open(str(mono)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2')/32768
    hop = 160
    power = np.convolve(x**2, np.ones(320)/320, 'same')[::hop]
    return mono, x, 10*np.log10(power+1e-12)


def _chunks(db, threshold=-42.):
    """Voiced stretches (s, e) of at most 25 s, split at the quietest moment."""
    voiced = db > threshold
    spans, start, quiet = [], None, 0
    for i, on in enumerate(voiced):
        if on:
            if start is None: start = i
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet > 50:
                spans.append((start, i-quiet+1)); start, quiet = None, 0
    if start is not None: spans.append((start, len(voiced)))
    out = []
    def split(a, b):
        if b-a <= 2500:
            if b-a > 20: out.append((max(0, a-15), b+15))
            return
        middle = a+1000+int(np.argmin(db[a+1000:b-1000])) if b-a > 2200 else (a+b)//2
        split(a, middle); split(middle, b)
    for a, b in spans: split(a, b)
    return out


def _transcribe(mono, x, db, folder):
    """One word list with times checked against the voice's own energy (whisper's token times drift)."""
    tool = tools.whisper()
    if not tool: return None
    binary, model = tool
    parts = folder/'chunks'
    parts.mkdir(exist_ok=True)
    spans = _chunks(db)
    if not spans: return []
    files = []
    for n, (a, b) in enumerate(spans):
        path = parts/f'c{n:04d}.wav'
        with wave.open(str(path), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes((np.clip(x[a*160:b*160], -1, 1)*32767).astype('<i2').tobytes())
        files.append(path)
    command = [binary, '-m', model, '-l', 'en', '-ml', '1', '-sow', '-ojf', '-np', '--prompt', 'Um, uh, so, like, you know, I mean.']  # the prompt keeps ums in the transcript so they can be cut
    for path in files: command += ['-f', str(path)]
    subprocess.run(command, timeout=3600, **RUN)
    words = []
    for (a, b), path in zip(spans, files):
        result = Path(str(path)+'.json')
        if not result.is_file(): continue
        for segment in json.loads(result.read_text()).get('transcription', []):
            text = segment['text'].strip()
            if not text or text.startswith(('[', '(')) or text == '-': continue
            words.append({'w': text, 's': a/100+segment['offsets']['from']/1000, 'e': a/100+segment['offsets']['to']/1000, 'chunk_end': b/100})
    shutil.rmtree(parts, ignore_errors=True)
    # Snap each start to the nearest rise in energy, keep order, end each word where the next begins or the voice stops.
    last = -1.
    for word in words:
        lo, hi = max(0, int((word['s']-.2)*100)), int((word['s']+.08)*100)
        if hi > lo+2:
            word['s'] = (lo+int(np.argmax(np.diff(db[lo:hi])))+1)/100
        word['s'] = max(word['s'], last+.05); last = word['s']
    for word, following in zip(words, [*words[1:], None]):
        limit = following['s'] if following else word['chunk_end']
        word['e'] = round(min(limit, max(word['e'], word['s']+.08)), 3)
        tail = int(word['e']*100)
        while tail > int(word['s']*100)+5 and tail < len(db) and db[tail] < -42: tail -= 1  # do not hold silence as a word
        word['e'] = round(max(tail/100+.04, word['s']+.08), 3); word['s'] = round(word['s'], 3)
        del word['chunk_end']
    return words


def _faster_whisper(path):
    """Word times from faster-whisper when whisper-cli is not installed (the model downloads once)."""
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return None
    import os
    model = WhisperModel(os.getenv('CASCADE_WHISPER_MODEL', 'small'), device='cpu', compute_type='int8')
    pcm = subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-i', str(path), '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'], capture_output=True, timeout=900).stdout
    segments, _ = model.transcribe(np.frombuffer(pcm, np.float32), language='en', word_timestamps=True, condition_on_previous_text=False,
                                   initial_prompt='Um, uh, so, like, you know.')
    return [{'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3)} for s in segments for w in s.words if w.word.strip()]


def _from_cues(cues):
    """Without whisper: spread the existing transcript's words through each cue."""
    words = []
    for cue in cues:
        parts = cue['text'].split()
        if not parts: continue
        step = (cue['end']-cue['start'])/len(parts)
        words += [{'w': w, 's': round(cue['start']+i*step, 3), 'e': round(cue['start']+(i+1)*step, 3)} for i, w in enumerate(parts)]
    return words


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


def prepare(source, cues, folder, progress, separate=True):
    """Returns the measurements; cached in `folder` for the life of the clip. `separate=False` skips
    voice separation (the Cinema engine edits the clip's own sound and does not need it)."""
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    done = folder/'prep.json'
    stat = Path(source).stat()
    stamp = [stat.st_size, stat.st_mtime_ns]
    if done.is_file():
        saved = json.loads(done.read_text())
        if saved.get('stamp') == stamp and (saved.get('separated', True) or not separate): return saved
    media = probe(source)
    if not media['width']: raise ValueError('This clip has no video.')
    if not media['has_audio']: raise ValueError('This clip has no sound, and this edit is built around what is said.')
    if separate:
        progress(.06, 'Separating the voices from any music in the clip…')
        voice, isolated = _voice(source, folder)
    else:
        voice = folder/'mix.wav'
        subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-y', '-i', str(source), '-vn', '-ac', '2', '-ar', '44100', str(voice)], check=True, timeout=600, **RUN)
        isolated = False
    progress(.2, 'Transcribing every word…')
    mono, x, db = _energy(voice, folder)
    words = _transcribe(mono, x, db, folder)
    if words is None:
        try:
            words = _faster_whisper(voice)
        except Exception:
            words = None
    if words is None: words = _from_cues(cues)
    if not words: raise ValueError('I could not find any speech in this clip to edit around.')
    progress(.28, 'Finding the shots…')
    cuts = _cuts(source)
    every = _sheets(source, media['duration'], folder)
    np.save(folder/'energy.npy', db.astype('float32'))
    saved = {**media, 'stamp': stamp, 'voice': Path(voice).name, 'isolated': isolated, 'separated': separate, 'words': [{**w, 'i': i} for i, w in enumerate(words)],
             'cuts': cuts, 'sheet_every': every, 'sheets': sorted(p.name for p in folder.glob('sheet*.jpg'))}
    done.write_text(json.dumps(saved))
    return saved
