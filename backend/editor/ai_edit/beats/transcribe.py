"""Stage 1: word-level transcription behind one function.

    transcribe(video) -> [{"word": str, "start": float, "end": float}, ...]

Audio is extracted with FFmpeg (16 kHz mono) and transcribed by the Whisper-family tools Cascade
already uses for AI edits (../prep.py): whisper-cli when installed (start times snapped to the
voice's own energy), otherwise faster-whisper (CASCADE_WHISPER_MODEL, default "small"). Deepgram
cue text is not used here because it has no per-word times.

Results are cached in `workdir` against the video's size and modification time.

Check against a reference transcript from the repository root:

    python -m backend.editor.ai_edit.beats.transcribe VIDEO \
        --reference backend/editor/ai_edit/beats/examples/transcript_full.json
"""
import argparse
import difflib
import json
import re
import statistics
import tempfile
from pathlib import Path

from .. import prep

EXAMPLES = Path(__file__).parent/'examples'


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
    raw, engine = prep._transcribe(mono, samples, db, folder), 'whisper-cli'
    if raw is None:
        raw, engine = prep._faster_whisper(mono), 'faster-whisper'
    if raw is None:
        raise TranscriptionUnavailable('No word-level transcriber is installed. Install faster-whisper '
                                       '(pip install faster-whisper) or whisper-cli.')
    words = normalize(raw)
    if not words: raise TranscriptionUnavailable('No speech was found in this video.')
    cache.write_text(json.dumps({'stamp': stamp, 'engine': engine, 'words': words}))
    report(1, 'Transcribed.')
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
