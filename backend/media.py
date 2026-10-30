"""Shared audio/video probing and normalization; source.video stays the job contract."""
import json
import math
import subprocess
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


def normalize_media(path, info=None):
    """Convert only when browser/encoder compatibility needs it; preserve the original."""
    path = Path(path)
    info = info or probe_media(path)
    compatible = (info['has_video'] and info['video_codec'] == 'h264'
                  and (not info['has_audio'] or info['audio_codec'] == 'aac')
                  and info.get('pixel_format') == 'yuv420p'
                  and 'mp4' in info['container'] and info.get('brand') != 'qt') or (not info['has_video'] and info['audio_codec'] == 'mp3' and info['container'] == 'mp3')
    if compatible:
        return info
    suffix = '.mp4' if info['has_video'] else '.mp3'
    target = path.with_name('normalized'+suffix)
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-i', str(path)]
    if info['has_video']:
        command += ['-map', f"0:{info['video_stream_index']}", '-map', '0:a:0?']
        if info['video_codec'] == 'h264' and info.get('pixel_format') == 'yuv420p' and (not info['has_audio'] or info['audio_codec'] == 'aac'):
            command += ['-c', 'copy', '-movflags', '+faststart']
        else:
            command += ['-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-c:v', 'libx264', '-preset', 'veryfast',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart']
    else:
        command += ['-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '192k']
    try:
        subprocess.run(command+[str(target)], capture_output=True, check=True, timeout=600)
        normalized = probe_media(target)
        original = path.with_name('original-upload.media')
        if not original.exists():
            path.replace(original)
        target.replace(path)
        return normalized
    except (OSError, subprocess.SubprocessError):
        raise HTTPException(400, 'Media could not be decoded or normalized. Try another recording or re-export the file.') from None
    finally:
        target.unlink(missing_ok=True)


def content_type(filename):
    return 'audio/mpeg' if str(filename).endswith('.mp3') else 'text/vtt' if str(filename).endswith('.vtt') else 'video/mp4'
