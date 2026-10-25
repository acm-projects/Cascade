"""Shared source inspection and thumbnail rendering."""
from pathlib import Path
from backend import integration as store


def inspect_video(video):
    return store.host.inspect_video(video)


def make_thumbnail(video, out_jpg, at_seconds):
    out_jpg = Path(out_jpg)
    temporary = out_jpg.with_name(out_jpg.stem + '.tmp.jpg')
    try:
        store.host.run_command([
            'ffmpeg', '-y', '-v', 'error', '-ss', f'{at_seconds:.3f}',
            '-i', str(video), '-frames:v', '1', '-vf', 'scale=640:-2', str(temporary),
        ])
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ValueError('Could not create a video thumbnail.')
        temporary.replace(out_jpg)
    finally:
        temporary.unlink(missing_ok=True)
