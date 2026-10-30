"""Manual provider-backed evaluation: python scripts/eval_generation.py VIDEO --prompts FILE.

Uses configured transcription/LLM services. Existing source media is only read.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def spread_score(clips, duration):
    """Distinct quarters containing a selected clip's midpoint (0–4)."""
    return len({min(3, int(((c['start'] + c['end']) / 2) / duration * 4)) for c in clips}) if duration > 0 else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--prompts', type=Path, default=Path(__file__).with_name('eval_prompts.txt'))
    parser.add_argument('--count', type=int, default=4, choices=range(1, 51))
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    from backend.media import probe_media
    from backend.agent.website import select_with_agent
    duration = probe_media(args.video)['duration']
    print('prompt\tintent\ttimestamps\tspread_quarters', flush=True)
    for prompt in args.prompts.read_text(encoding='utf-8').splitlines():
        if not prompt.strip() or prompt.lstrip().startswith('#'):
            continue
        clips, _, meta = select_with_agent(args.video, duration, prompt, 30,
                                           lambda msg: print(msg, file=sys.stderr), lambda _: None,
                                           requested_count=args.count)
        print(f'{json.dumps(prompt)}\t{meta["intent"]}\t'
              + ', '.join(f'{c["start"]:.1f}-{c["end"]:.1f}s' for c in clips)
              + f'\t{spread_score(clips, duration)}/4', flush=True)


if __name__ == '__main__':
    main()
