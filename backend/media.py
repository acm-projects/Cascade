"""Shared audio/video probing and normalization; source.video stays the job contract."""
import json
import math
import os
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException

SUPPORTED_EXTENSIONS = {'.mp4', '.mov', '.webm', '.mkv', '.mp3', '.wav', '.m4a', '.flac', '.avi', '.m4v'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac'}
CONTAINERS = {'mov', 'mp4', 'm4a', '3gp', '3g2', 'mj2', 'matroska', 'webm', 'mp3', 'wav', 'flac', 'avi'}


def validate_filename(name):
    if Path(name or '').suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, 'Unsupported media. Choose MP4, MOV, WebM, MKV, MP3, WAV, M4A, or FLAC.')


def probe_media(path):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-show_format', '-show_streams', '-of', 'json', str(path)],
            capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        formats = set(data['format'].get('format_name', '').split(','))
        video = next((s for s in data['streams'] if s.get('codec_type') == 'video'
                      and not s.get('disposition', {}).get('attached_pic')), None)
        audio = next((s for s in data['streams'] if s.get('codec_type') == 'audio'), None)
        if not formats.intersection(CONTAINERS) or not math.isfinite(duration) or duration <= .05 or not (video or audio):
            raise ValueError()
        return {'duration': duration, 'has_video': video is not None, 'has_audio': audio is not None,
                'media_kind': 'video' if video else 'audio', 'width': (video or {}).get('width', 0),
                'height': (video or {}).get('height', 0), 'video_codec': (video or {}).get('codec_name'),
                'video_stream_index': (video or {}).get('index'), 'pixel_format': (video or {}).get('pix_fmt'),
                'audio_codec': (audio or {}).get('codec_name'), 'container': data['format'].get('format_name', ''),
                'brand': data['format'].get('tags', {}).get('major_brand', '').strip()}
    except FileNotFoundError:
        raise HTTPException(503, 'FFmpeg and ffprobe must be installed to process media.') from None
    except (ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise HTTPException(400, 'The media is corrupted, unsupported, or has no playable audio/video stream.') from None


def needs_conversion(info):
    """False when the media already plays in browsers and cuts without re-encoding (H.264/AAC MP4, or MP3)."""
    return not ((info['has_video'] and info['video_codec'] == 'h264'
                 and (not info['has_audio'] or info['audio_codec'] == 'aac')
                 and info.get('pixel_format') == 'yuv420p'
                 and 'mp4' in info['container'] and info.get('brand') != 'qt')
                or (not info['has_video'] and info['audio_codec'] == 'mp3' and info['container'] == 'mp3'))


def needs_reencode(info):
    """True when converting means re-encoding the video (slow), not just moving it into an MP4 (seconds)."""
    return info['has_video'] and not (info['video_codec'] == 'h264' and info.get('pixel_format') == 'yuv420p')


# A keyframe at least every 60 frames (~2s): a later smart cut then re-encodes at most that much per clip.
CPU_ENCODER = ('cpu', ['-c:v', 'libx264', '-preset', 'veryfast', '-g', '60', '-pix_fmt', 'yuv420p'])
GPU_ENCODERS = (
    # Quality levels picked to match the CPU encode's quality (SSIM ~0.993) at a similar file size.
    ('NVIDIA GPU', ['-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', '28', '-b:v', '0', '-g', '60', '-pix_fmt', 'yuv420p']),
    ('AMD GPU', ['-c:v', 'h264_amf', '-quality', 'balanced', '-rc', 'cqp', '-qp_i', '24', '-qp_p', '26', '-g', '60', '-pix_fmt', 'yuv420p']),
    ('Intel GPU', ['-c:v', 'h264_qsv', '-global_quality', '23', '-g', '60', '-pix_fmt', 'nv12']),
)


@lru_cache(maxsize=1)
def gpu_encoder():
    """The first hardware H.264 encoder that actually works on this machine (a tiny test encode), or None.
    CASCADE_VIDEO_ENCODER=cpu turns hardware encoding off."""
    if os.getenv('CASCADE_VIDEO_ENCODER', 'auto').strip().lower() == 'cpu':
        return None
    for name, args in GPU_ENCODERS:
        try:
            test = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=30:d=0.3',
                                   *args, '-f', 'null', '-'], capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
        if test.returncode == 0:
            return name, args
    return None


def convert_media(path, info, target, progress=lambda message: None):
    """Write a browser-ready copy of `path` to `target` and return its probe. Re-encoding uses a working
    GPU encoder when there is one and falls back to the CPU if it fails. `path` is only read."""
    path, target = Path(path), Path(target)
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-i', str(path)]
    # Long videos on a CPU can take a while: allow about real time, never less than 10 minutes.
    timeout = max(600, info.get('duration', 0))
    if not info['has_video']:
        attempts = [('audio', command + ['-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '192k', str(target)])]
    elif not needs_reencode(info):
        audio = ['-c:a', 'copy'] if not info['has_audio'] or info['audio_codec'] == 'aac' else ['-c:a', 'aac']
        attempts = [('copy', command + ['-map', f"0:{info['video_stream_index']}", '-map', '0:a:0?', '-c:v', 'copy',
                                        *audio, '-movflags', '+faststart', str(target)])]
    else:
        video = command + ['-map', f"0:{info['video_stream_index']}", '-map', '0:a:0?',
                           '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2']
        encoders = [e for e in (gpu_encoder(), CPU_ENCODER) if e]
        attempts = [(name, video + args + ['-c:a', 'aac', '-movflags', '+faststart', str(target)]) for name, args in encoders]
    for number, (name, attempt) in enumerate(attempts, start=1):
        try:
            subprocess.run(attempt, capture_output=True, check=True, timeout=timeout)
            return {**probe_media(target), 'encoder': name}
        except (OSError, subprocess.SubprocessError):
            target.unlink(missing_ok=True)
            if number < len(attempts):
                progress(f'{name} encoding failed; converting on the CPU instead')
    raise HTTPException(400, 'Media could not be decoded or normalized. Try another recording or re-export the file.')


def replace_with_converted(path, target):
    """Keep the original as original-upload.media and put the converted file in its place. Windows refuses
    to rename a file another program has open (a browser streaming it), so this retries for a while."""
    path, target = Path(path), Path(target)
    original = path.with_name('original-upload.media')
    for _ in range(60):
        try:
            if not original.exists():
                path.replace(original)
            target.replace(path)
            return
        except PermissionError:
            time.sleep(0.5)
    if not path.exists() and original.exists():
        original.replace(path)  # never leave the project without its source
    raise HTTPException(503, 'The converted video could not replace the original. Retry the analysis.')


def normalize_media(path, info=None):
    """Convert only when browser/encoder compatibility needs it; preserve the original."""
    path = Path(path)
    info = info or probe_media(path)
    if not needs_conversion(info):
        return info
    target = path.with_name('normalized' + ('.mp4' if info['has_video'] else '.mp3'))
    try:
        normalized = convert_media(path, info, target)
        replace_with_converted(path, target)
        return normalized
    finally:
        target.unlink(missing_ok=True)


def content_type(filename):
    return 'audio/mpeg' if str(filename).endswith('.mp3') else 'text/vtt' if str(filename).endswith('.vtt') else 'video/mp4'
