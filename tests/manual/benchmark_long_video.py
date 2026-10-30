"""Long-video smoke/benchmark. --fixture is offline and does not assess AI quality.

Examples:
  python tests/manual/benchmark_long_video.py --fixture --output .test-tmp/long-video
  python tests/manual/benchmark_long_video.py --source documentary.mp4 --live --output .test-tmp/documentary

--live uses configured transcription/AI services and may incur charges.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def make_fixture(path):
    args = ['ffmpeg', '-nostdin', '-v', 'error', '-y']
    for color in ('blue', 'green', 'red', 'yellow'):
        args += ['-f', 'lavfi', '-i', f'color=c={color}:s=320x180:r=1/5:d=1950']
    args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=8000:duration=7800',
             '-filter_complex', '[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]',
             '-map', '[v]', '-map', '4:a', '-c:v', 'libx264', '-preset', 'ultrafast',
             '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '24k', '-movflags', '+faststart', str(path)]
    subprocess.run(args, check=True, timeout=300)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture', action='store_true')
    mode.add_argument('--source', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--min-seconds', type=float, default=7200,
                        help='Minimum source duration; use 0 to benchmark a shorter user-selected file honestly.')
    parser.add_argument('--prompt', default='Find four important historical or public-health explanations from across this documentary.')
    args = parser.parse_args()
    if args.fixture and args.live:
        parser.error('--fixture is offline; use --source with --live for real documentary evaluation.')
    if args.source and not args.live:
        parser.error('Real source evaluation requires explicit --live (paid providers).')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.fixture:
        os.environ['PYTHON_DOTENV_DISABLED'] = '1'
        source = root / 'fixture-2h10m.mp4'
        if not source.exists():
            make_fixture(source)
    else:
        source = args.source.resolve()
    import app1
    from backend.core import jobs as core_jobs
    from backend.routers import clips as clip_routes
    from backend.media import probe_media
    from backend.generation import reuse_source
    info = probe_media(source)
    if info['duration'] < args.min_seconds:
        raise RuntimeError(f'Use a source at least {args.min_seconds:g} seconds long, or set --min-seconds explicitly.')
    job_id = uuid4().hex
    jobs = root / 'jobs'
    folder = jobs / job_id
    folder.mkdir(parents=True)
    reuse_source(source, folder / 'source.video')

    def fixture_selection(video_path, duration, search, target, progress, stage, **kwargs):
        stage('Offline deterministic selection (no AI)')
        windows = [10., 2600., 5200., 7600.]
        return ([{'start': t, 'end': t + 20, 'title': f'Fixture quarter {i + 1}',
                  'explanation': 'Synthetic media mechanics test, not a documentary match.'} for i, t in enumerate(windows)],
                [{'start': t, 'end': t + 18, 'text': f'Fixture caption {i + 1}'} for i, t in enumerate(windows)],
                {'model': 'offline-fixture', 'selection_mode': 'mocked', 'selection_note': ''})

    started = time.perf_counter()
    with patch.object(core_jobs, 'JOBS_DIR', jobs), patch.dict(os.environ, {
        'CASCADE_STORAGE': 'local', 'CASCADE_METADATA_STORE': 'local', 'CASCADE_WARM_MODELS': '0'}):
        core_jobs.save_json(folder / 'owner.json', {'user_id': 'benchmark-fixture', 'user_folder': 'users',
            'requested_clip_count': 4, 'source_job': job_id, 'media_kind': 'video'})
        core_jobs.jobs[job_id] = {'state': 'queued', 'clips': []}
        with patch.object(clip_routes, 'select_with_agent', side_effect=fixture_selection) if args.fixture else patch.dict({}, {}):
            clip_routes.process_upload(job_id, folder / 'source.video', args.prompt, 'both', 30)
        processing_seconds = round(time.perf_counter() - started, 3)
        job = core_jobs.jobs.pop(job_id)
        if job['state'] != 'done':
            raise RuntimeError(job.get('message', 'Generation failed'))
        result = core_jobs.load_json(folder / 'results.json')
        checks = []
        for i, clip in enumerate(result['clips'], 1):
            output = probe_media(folder / f'clip_{i}.mp4')
            captions = (folder / f'clip_{i}.vtt').read_text()
            assert 0 <= clip['start'] < clip['end'] <= info['duration']
            assert abs(output['duration'] - (clip['end'] - clip['start'])) < 1.0
            assert captions.startswith('WEBVTT')
            checks.append({'start': clip['start'], 'end': clip['end'], 'rendered_seconds': output['duration'],
                           'title': clip.get('title', ''), 'explanation': clip.get('explanation', ''),
                           'file': str(folder / f'clip_{i}.mp4')})
            if args.fixture:
                frame = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(folder / f'clip_{i}.mp4'),
                    '-frames:v', '1', '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                    capture_output=True, check=True, timeout=30).stdout
                expected = [(0, 0, 255), (0, 128, 0), (255, 0, 0), (255, 255, 0)][i - 1]
                assert len(frame) == 3 and max(abs(a - b) for a, b in zip(frame, expected)) < 20
                checks[-1]['verified_frame_rgb'] = list(frame)
    report = {'mode': 'offline synthetic mechanics; AI mocked' if args.fixture else 'live documentary',
              'source_seconds': info['duration'], 'pipeline_processing_seconds': processing_seconds,
              'includes_browser_upload': False,
              'first_clip_ready_seconds': result.get('first_clip_ready_seconds'), 'timings': result.get('timings'),
              'index_timings': result.get('index_timings'), 'selection_mode': result.get('selection_mode'), 'clips': checks}
    (root / 'benchmark.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
