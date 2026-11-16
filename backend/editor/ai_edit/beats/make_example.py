"""Render the kit's example end to end without the app or any model:

    python -m backend.editor.ai_edit.beats.make_example [--plan PLAN] [--source VIDEO] [--out MP4]

Plan: examples/edit_plan_example.json (validated for this video). Source: examples/source/source.mov.
Writes output/final_edit.mp4 and output/final_edit.report.json. Uses PEXELS_API_KEY for b-roll when set.
Work files (proxy, cut-outs, cached beat segments) go to output/work, so a second run re-renders only what changed.
"""
import argparse
import json
import time
from pathlib import Path

from backend import broll as stocklib

from . import assets, render

HERE = Path(__file__).parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--plan', default=str(HERE/'examples'/'edit_plan_example.json'))
    parser.add_argument('--source', default=str(HERE/'examples'/'source'/'source.mov'))
    parser.add_argument('--out', default=str(HERE/'output'/'final_edit.mp4'))
    parser.add_argument('--work', default=str(HERE/'output'/'work'))
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text())
    store = stocklib.Store(Path(args.work)/'stock')
    started = time.time()
    report = render.render(plan, args.source, args.out, args.work, audio=assets.mix,
                           make_assets=lambda work, size: assets.prepare(plan, work, store, (), size),
                           progress=lambda amount, stage: print(f'{amount:4.0%} {stage}', flush=True))
    report['wall_seconds'] = round(time.time()-started, 1)
    Path(args.out).with_suffix('.report.json').write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ('frames', 'seconds', 'rendered_beats', 'timings', 'checks', 'wall_seconds')}, indent=1))


if __name__ == '__main__':
    main()
