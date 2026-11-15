"""Stage 1: word-level transcription behind one function.

    transcribe(video) -> [{"word": str, "start": float, "end": float}, ...]

Audio is extracted with FFmpeg (16 kHz mono) and transcribed by the first engine available:
  1. whisper-cli (start times snapped to the voice's own energy; ../prep.py)
  2. faster-whisper (CASCADE_WHISPER_MODEL, default "small"; the model downloads once)
  3. NVIDIA Parakeet TDT 0.6B through sherpa-onnx, adapted from reference/scripts/transcribe.py (the model that
     made examples/transcript_full.json). Model folder: CASCADE_PARAKEET_MODEL or
     ~/.cache/cascade/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8 (a GitHub release download).
CASCADE_TRANSCRIBER=whisper-cli|faster-whisper|parakeet forces one. Deepgram cue text is not used here
because it has no per-word times.

Results are cached in `workdir` against the video's size and modification time.

Check against a reference transcript from the repository root:

    python -m backend.editor.ai_edit.beats.transcribe VIDEO \
        --reference backend/editor/ai_edit/beats/examples/transcript_full.json
"""
import argparse
import difflib
import json
import logging
import os
import re
import statistics
import tempfile
from pathlib import Path

from .. import prep

EXAMPLES = Path(__file__).parent/'examples'
LOG = logging.getLogger(__name__)


class TranscriptionUnavailable(RuntimeError):
    """No word-level transcriber is installed, or the audio has no speech."""


def transcribe(video, workdir=None, progress=None):
    """Word-level transcript of `video`: [{word, start, end}] in seconds, sorted, rounded to 0.01 s."""
    report = progress or (lambda amount, stage: None)
    video = Path(video)
    if not video.is_file(): raise FileNotFoundError(f'No video at {video}')
    folder = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix='beats-transcribe-'))
    folder.mkdir(parents=True, exist_ok=True)
    stat = video.stat()
    stamp = [stat.st_size, stat.st_mtime_ns]
    cache = folder/'transcript.json'
    if cache.is_file():
        try:
            saved = json.loads(cache.read_text())
            if saved.get('stamp') == stamp: return saved['words']
        except (OSError, ValueError, KeyError):
            pass
    report(.05, 'Getting the audio ready…')
    mono, samples, db = prep._energy(video, folder)   # FFmpeg -> 16 kHz mono wav, plus energy every 10 ms
    report(.2, 'Transcribing every word…')
    raw, engine = None, None
    for engine, run in _engines():
        try:
            raw = run(mono, samples, db, folder)
        except Exception:   # a missing model download is not fatal while another engine is left
            LOG.info('%s could not transcribe', engine, exc_info=True)
            raw = None
        if raw is not None: break
    if raw is None:
        raise TranscriptionUnavailable('No word-level transcriber is available. Install faster-whisper '
                                       '(pip install faster-whisper), whisper-cli, or sherpa-onnx with the Parakeet model.')
    words = normalize(raw)
    if not words: raise TranscriptionUnavailable('No speech was found in this video.')
    cache.write_text(json.dumps({'stamp': stamp, 'engine': engine, 'words': words}))
    LOG.info('transcribed %d words with %s', len(words), engine)
    report(1, 'Transcribed.')
    return words


def _engines():
    engines = [('whisper-cli', prep._transcribe), ('faster-whisper', lambda mono, *_: prep._faster_whisper(mono)),
               ('parakeet', lambda mono, *_: parakeet(mono))]
    forced = os.getenv('CASCADE_TRANSCRIBER', '').strip().lower()
    return [e for e in engines if e[0] == forced] if forced else engines


PARAKEET = 'sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8'


def parakeet_model():
    for folder in (os.getenv('CASCADE_PARAKEET_MODEL', ''), Path.home()/'.cache'/'cascade'/PARAKEET):
        if folder and (Path(folder)/'tokens.txt').is_file(): return Path(folder)
    return None


def parakeet(mono):
    """Words from Parakeet (reference/scripts/transcribe.py, made a function): ~25 s chunks cut at the quietest 100 ms,
    a word starts at its first token, and ends at the next word's start (at most 0.6 s later)."""
    folder = parakeet_model()
    if folder is None: return None
    import wave

    import numpy as np
    import sherpa_onnx
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(folder/'encoder.int8.onnx'), decoder=str(folder/'decoder.int8.onnx'), joiner=str(folder/'joiner.int8.onnx'),
        tokens=str(folder/'tokens.txt'), num_threads=max(1, min(4, os.cpu_count() or 1)), model_type='nemo_transducer', decoding_method='greedy_search')
    with wave.open(str(mono)) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)/32768
    duration = len(x)/rate
    hop = int(.1*rate)
    energy = np.array([np.sqrt(np.mean(x[i:i+hop]**2)) for i in range(0, max(1, len(x)-hop), hop)])
    bounds, t = [0.], 25.
    while t < duration-8:
        lo, hi = int((t-3)/.1), int((t+3)/.1)
        k = lo+int(np.argmin(energy[lo:hi])); bounds.append(k*.1); t = k*.1+25.
    bounds.append(duration)
    words = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        stream = recognizer.create_stream(); stream.accept_waveform(rate, x[int(a*rate):int(b*rate)]); recognizer.decode_stream(stream)
        current = None
        for token, at in zip(stream.result.tokens, stream.result.timestamps):
            if token.startswith(('\u2581', ' ')) or current is None:
                if current: words.append(current)
                current = {'w': token.lstrip('\u2581 '), 's': round(a+at, 2)}
            else:
                current['w'] += token
        if current: words.append(current)
    words = [w for w in words if w['w']]
    for i, word in enumerate(words):
        following = words[i+1]['s'] if i+1 < len(words) else duration
        word['e'] = round(min(following, word['s']+.6), 2)
    return words


def normalize(raw):
    """Cascade's internal {w, s, e} (or {word, start, end}) words -> sorted {word, start, end}, never overlapping."""
    words = []
    for item in raw:
        text = str(item.get('word', item.get('w', ''))).strip()
        start = item.get('start', item.get('s'))
        end = item.get('end', item.get('e'))
        if not text or start is None or end is None: continue
        words.append({'word': text, 'start': float(start), 'end': float(end)})
    words.sort(key=lambda w: w['start'])
    for word, following in zip(words, [*words[1:], None]):
        if following and word['end'] > following['start']: word['end'] = following['start']
        word['end'] = max(word['end'], word['start'])
        word['start'], word['end'] = round(word['start'], 2), round(word['end'], 2)
    return words


def _token(text):
    return re.sub(r"[^a-z0-9']", '', text.lower())


def compare(words, reference, tolerance=.3):
    """Match words to a reference transcript by their text and measure the timing difference.

    `passed` means at least 90% of the reference words were matched and at least 95% of the matched
    start times are within `tolerance` seconds."""
    ours = [_token(w['word']) for w in words]
    theirs = [_token(w['word']) for w in reference]
    matcher = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    pairs = [(words[block.a+k], reference[block.b+k]) for block in matcher.get_matching_blocks() for k in range(block.size)
             if theirs[block.b+k]]
    if not pairs:
        return {'reference_words': len(reference), 'words': len(words), 'matched': 0, 'coverage': 0., 'passed': False}
    starts = sorted(abs(a['start']-b['start']) for a, b in pairs)
    ends = sorted(abs(a['end']-b['end']) for a, b in pairs)
    pct = lambda values, q: values[min(len(values)-1, int(round(q*(len(values)-1))))]
    within = sum(d <= tolerance+1e-9 for d in starts)/len(starts)
    coverage = len(pairs)/max(1, sum(1 for t in theirs if t))
    worst = sorted(pairs, key=lambda p: -abs(p[0]['start']-p[1]['start']))[:5]
    return {
        'reference_words': len(reference), 'words': len(words), 'matched': len(pairs), 'coverage': round(coverage, 3),
        'tolerance': tolerance, 'start_within': round(within, 3),
        'start_median': round(statistics.median(starts), 3), 'start_p95': round(pct(starts, .95), 3), 'start_max': round(starts[-1], 3),
        'end_median': round(statistics.median(ends), 3), 'end_within': round(sum(d <= tolerance+1e-9 for d in ends)/len(ends), 3),
        'worst': [{'word': b['word'], 'ours': a['start'], 'reference': b['start']} for a, b in worst],
        'passed': coverage >= .9 and within >= .95,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Word-level transcript of a video, optionally checked against a reference.')
    parser.add_argument('video')
    parser.add_argument('--reference', help='reference transcript JSON ([{word,start,end}]) to compare with')
    parser.add_argument('--out', help='write the transcript JSON here')
    parser.add_argument('--workdir', help='folder for the extracted audio and the cache')
    parser.add_argument('--tolerance', type=float, default=.3)
    args = parser.parse_args(argv)
    words = transcribe(args.video, args.workdir, lambda amount, stage: print(f'{amount:>4.0%} {stage}'))
    print(f'{len(words)} words, {words[0]["start"]:.2f}s to {words[-1]["end"]:.2f}s')
    if args.out: Path(args.out).write_text(json.dumps(words, indent=1))
    if args.reference:
        result = compare(words, json.loads(Path(args.reference).read_text()), args.tolerance)
        print(json.dumps(result, indent=1))
        return 0 if result['passed'] else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
