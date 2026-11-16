"""Stage 6: side-by-side contact sheets of the reference edit and our render, for judging the style by eye.

    python -m backend.editor.ai_edit.beats.compare --ref reference/inspo.mov --ours output/final_edit.mp4 \
        --plan examples/edit_plan_example.json --out output/side_by_side

Two sheets:
  matched.jpg       each reference look next to our beat that uses the same template (mid-beat and entrance)
  proportional.jpg  the same relative moments (5 %, 13 %, ... 95 %) of both videos
The reference is a screen recording of an app panel: only its video area (REF_CROP) is used.
"""
import argparse
import json
import subprocess
from pathlib import Path

REF_CROP = (4, 90, 1276, 718)   # x, y, w, h of the edited video inside reference/inspo.mov
CELL = 480

# Reference moments (seconds in inspo.mov) and the template that shows the same idea.
MATCHED = [
    (0.70, 'TEXT_BEHIND_SUBJECT', 'giant word behind the speaker'),
    (2.20, 'KINETIC_KEYWORD', 'keyword + serif accent, glow'),
    (4.00, 'SPEAKER_CUTOUT_ICONS', 'cut-out speaker + icons'),
    (6.90, 'BROLL_OVERLAY', 'b-roll behind the keyword'),
    (9.40, 'SCRIBBLE_HIGHLIGHT', 'hand-drawn circle + strike'),
    (10.60, 'COLLAGE', 'tilted cards'),
    (5.70, 'NUMBER_COUNTER', 'number counter + chart line'),
    (1.00, 'TRANSITION', 'cut with motion blur'),
]


def grab(video, seconds, label, out, crop=None, colour='yellow'):
    crop_filter = f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},' if crop else ''
    text = label.replace(':', r'\:').replace("'", '')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', f'{max(0, seconds):.3f}', '-i', str(video), '-frames:v', '1',
                    '-vf', f"{crop_filter}scale={CELL}:270:force_original_aspect_ratio=decrease,pad={CELL}:270:(ow-iw)/2:(oh-ih)/2,"
                           f"drawtext=text='{text}':x=6:y=6:fontsize=15:fontcolor={colour}:box=1:boxcolor=black@0.7", str(out)],
                   check=True, capture_output=True, timeout=120)


def tile(cells, columns, out):
    listing = [str(c) for c in cells]
    inputs = sum((['-i', c] for c in listing), [])
    rows = (len(listing)+columns-1)//columns
    layout = '|'.join(f'{(i % columns)*CELL}_{(i//columns)*270}' for i in range(len(listing)))
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', *inputs, '-filter_complex',
                    f"xstack=inputs={len(listing)}:layout={layout}:fill=black", '-frames:v', '1', '-q:v', '3', str(out)],
                   check=True, capture_output=True, timeout=300)
    return out


def duration(video):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(video)], capture_output=True, text=True)
    return float(out.stdout.strip())


def sheets(ref, ours, plan, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    cells = out/'cells'; cells.mkdir(exist_ok=True)
    origin = plan['source_window']['start']
    matched, pairs = [], []
    for n, (at, template, what) in enumerate(MATCHED):
        if template == 'TRANSITION':
            beat = next((b for b in plan['beats'][1:] if b['transition_in'] == 'whip_pan'), plan['beats'][1])
            ours_at = beat['start']-origin+3/60
        else:
            beat = next((b for b in plan['beats'] if b['template'] == template), None)
            if beat is None: continue
            ours_at = (beat['start']+beat['end'])/2-origin
        a, b = cells/f'm{n}r.png', cells/f'm{n}o.png'
        grab(ref, at, f'REFERENCE {at:.1f}s: {what}', a, REF_CROP, 'cyan')
        grab(ours, ours_at, f"OURS beat {beat['id']} {template.lower()} {ours_at:.1f}s", b)
        matched += [a, b]
        pairs.append({'reference_seconds': at, 'ours_seconds': round(ours_at, 2), 'beat': beat['id'], 'template': template, 'what': what})
    tile(matched, 2, out/'matched.jpg')
    ref_len, our_len = duration(ref), duration(ours)
    prop = []
    for n, f in enumerate((.05, .13, .21, .29, .37, .45, .53, .61, .69, .77, .85, .95)):
        a, b = cells/f'p{n}r.png', cells/f'p{n}o.png'
        grab(ref, f*ref_len, f'REFERENCE {f:.0%}', a, REF_CROP, 'cyan')
        grab(ours, f*our_len, f'OURS {f:.0%}', b)
        prop += [a, b]
    tile(prop, 4, out/'proportional.jpg')
    (out/'pairs.json').write_text(json.dumps(pairs, indent=1))
    return out/'matched.jpg', out/'proportional.jpg'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--ref', required=True); parser.add_argument('--ours', required=True)
    parser.add_argument('--plan', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    for path in sheets(args.ref, args.ours, json.loads(Path(args.plan).read_text()), args.out): print(path)


if __name__ == '__main__':
    main()
