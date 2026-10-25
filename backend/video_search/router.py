from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
import shutil
import subprocess
import os
import threading

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sentence_transformers import SentenceTransformer
from backend.pipeline_timing import StageTimer
from backend.cascade_stt import TranscriptionError, transcribe_media

router = APIRouter()

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUTS = PROJECT_DIR / "outputs"
OUTPUTS.mkdir(exist_ok=True)

search_model = visual_model = None
_model_lock = threading.Lock()


def load_models(mode, progress=lambda message: None):
    global search_model, visual_model
    # One lock: the startup warm-up and an early upload never load the same model twice.
    with _model_lock:
        if mode == "speech" and search_model is None:
            progress('Loading speech search model (first use may download model files)...')
            search_model = SentenceTransformer("all-MiniLM-L6-v2")
        if mode == "visual" and visual_model is None:
            progress('Loading visual search model (first use may download model files)...')
            visual_model = SentenceTransformer("sentence-transformers/clip-ViT-B-32")


# Note: the standalone "/" page is now served via StaticFiles at /search-ui
# (see app1.py) instead of a dedicated route here, since this router
# is mounted under /api/search alongside the other features' APIs.


def transcribe(path, work, progress):
    """Deepgram transcript segments; a transcription failure becomes a clear 503 for the caller."""
    try:
        return transcribe_media(path, work, progress)
    except TranscriptionError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/clips/{filename}")
def get_clip(filename: str):
    clip = OUTPUTS / filename

    if clip.suffix != ".mp4" or not clip.is_file():
        raise HTTPException(status_code=404, detail="Clip not found")

    return FileResponse(clip, media_type="video/mp4")


def get_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


@router.post("/upload")
async def upload_video(
    video: UploadFile = File(...),
    search: str = Form(...),
    mode: str = Form("speech"),
    clip_length: int = Form(15),
):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(search_video, video, search, mode, clip_length)


def search_video(video, search, mode, clip_length, progress=lambda message: None, timing=lambda timings, active: None, requested_count=4, parent_context=None, followup_prompt=None):
    from backend.video_search.selection import select_matches
    import numpy as np
    timer = StageTimer(timing)
    if not search.strip():
        raise HTTPException(400, 'Type what you want to find.')
    if mode not in ('speech', 'visual') or clip_length not in (15, 30, 60):
        raise HTTPException(400, 'Choose speech/visual search and a 15, 30, or 60 second clip length.')
    if shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None:
        raise HTTPException(500, 'FFmpeg and ffprobe must be installed.')

    def run(command, timeout=300):
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)

    progress('Loading search models...')
    timer.start('Search model loading')
    load_models(mode, progress)
    outputs = []
    created = []
    try:
        with TemporaryDirectory() as folder:
            work = Path(folder)
            source = work / ('uploaded' + (Path(video.filename or 'source.mp4').suffix or '.mp4'))
            timer.start('Video preparation')
            with source.open('wb') as destination:
                shutil.copyfileobj(video.file, destination)
            duration = get_duration(source)
            if not np.isfinite(duration) or duration <= 0:
                raise HTTPException(400, 'Could not read a valid video duration.')
            transcript = []
            if mode == 'speech':
                timer.start('Deepgram transcription')
                progress('Transcribing video for speech search...')
                transcript = [{'start': s['start'], 'end': s['end'], 'text': s['text']}
                              for s in transcribe(source, work, progress)]
                if not transcript:
                    raise HTTPException(400, 'No speech was found in this video.')
                timer.start('Text embeddings')
                progress('Comparing your prompt with transcript segments...')
                embeddings = search_model.encode([part['text'] for part in transcript])
                query = search_model.encode(search)
                scores = search_model.similarity(query, embeddings).reshape(-1).tolist()
                anchors = [{'time': (part['start'] + part['end']) / 2, 'score': float(score),
                            'evidence_start': part['start'], 'evidence_end': part['end'], 'match': part['text']}
                           for part, score in zip(transcript, scores)]
            else:
                interval = max(3., duration / 100)
                timer.start('Frame extraction')
                progress('Extracting up to 100 preview frames across the video...')
                frames = work / 'frames'
                frames.mkdir()
                run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-vf',
                     (f'fps=1/{interval},' if duration >= interval else '') + 'scale=320:-2',
                     '-frames:v', '100' if duration >= interval else '1', str(frames / 'frame_%04d.jpg')])
                paths = sorted(frames.glob('frame_*.jpg'))
                if not paths:
                    raise HTTPException(400, 'No preview frames could be extracted.')
                timer.start('Prompt embedding')
                query = visual_model.encode(search, normalize_embeddings=True)
                embeddings = []
                for offset in range(0, len(paths), 8):
                    timer.start('Image decoding')
                    images = []
                    try:
                        for path in paths[offset:offset + 8]:
                            with Image.open(path) as image:
                                images.append(image.convert('RGB'))
                        timer.start('Image embeddings')
                        progress(f'Comparing video frames {offset + 1}–{min(offset + 8, len(paths))}/{len(paths)}...')
                        embeddings.extend(visual_model.encode(images, normalize_embeddings=True))
                    finally:
                        for image in images:
                            image.close()
                scores = np.asarray(embeddings) @ query
                anchors = [{'time': min(duration - .001, (index + .5) * interval) if duration >= interval else 0.,
                            'score': float(score), 'match': f'Visual match near {min(duration, (index + .5) * interval):.1f} seconds'}
                           for index, score in enumerate(scores)]

            timer.start('Match selection')
            progress(f'Selecting up to {requested_count} distinct non-overlapping matches...')
            selected = select_matches(anchors, duration, clip_length, 3 if mode == 'speech' else 5, limit=requested_count)
            from backend.generation import finalize_selections
            selected = finalize_selections(selected, parent_context, followup_prompt or search, duration, clip_length, requested_count)
            has_audio = False
            if mode == 'visual' and selected:
                timer.start('Audio inspection')
                probe = run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=index',
                             '-of', 'csv=p=0', str(source)], 30)
                has_audio = bool(probe.stdout.strip())

            for number, selection in enumerate(selected, 1):
                clip_start, clip_end = selection['start'], selection['end']
                clip_transcript = transcript
                if mode == 'visual':
                    clip_transcript = []
                    if has_audio:
                        timer.start('Audio extraction')
                        progress(f'Preparing captions for clip {number}/{len(selected)}...')
                        audio = work / f'selected_{number}.wav'
                        run(['ffmpeg', '-v', 'error', '-y', '-ss', str(clip_start), '-i', str(source), '-t',
                             str(clip_end - clip_start), '-vn', '-ac', '1', '-ar', '16000', str(audio)], 120)
                        timer.start('Deepgram transcription')
                        clip_transcript = [{'start': s['start'] + clip_start, 'end': s['end'] + clip_start, 'text': s['text']}
                                           for s in transcribe(audio, work, progress)]
                timer.start('Caption preparation')
                subtitle_lines, vtt_lines = [], ['WEBVTT\n']
                for part in clip_transcript:
                    start, end = max(part['start'], clip_start), min(part['end'], clip_end)
                    if end <= start:
                        continue
                    local_start, local_end = srt_time(start - clip_start), srt_time(end - clip_start)
                    subtitle_lines.append(f"{len(subtitle_lines) + 1}\n{local_start} --> {local_end}\n{part['text']}\n")
                    vtt_lines.append(f"{local_start.replace(',', '.')} --> {local_end.replace(',', '.')}\n{part['text']}\n")
                subtitle_name = f'captions_{number}.srt'
                if subtitle_lines:
                    (work / subtitle_name).write_text('\n'.join(subtitle_lines), encoding='utf-8')
                filename = uuid4().hex + '.mp4'
                output = OUTPUTS / filename
                created.append(output)
                command = ['ffmpeg', '-v', 'error', '-y', '-ss', str(clip_start), '-i', str(source),
                           '-t', str(clip_end - clip_start), '-map', '0:v:0', '-map', '0:a:0?']
                filters = ['scale=trunc(iw/2)*2:trunc(ih/2)*2']
                if subtitle_lines:
                    from backend.video_tools import subtitle_ffmpeg
                    command[0] = subtitle_ffmpeg()
                    filters.append('subtitles=filename=' + subtitle_name)
                command += ['-vf', ','.join(filters), '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', '-movflags', '+faststart', str(output)]
                timer.start('Video rendering')
                progress(f'Rendering clip {number}/{len(selected)} with audio and captions...')
                subprocess.run(command, cwd=work, check=True, capture_output=True, text=True,
                               timeout=float(os.getenv('CASCADE_FFMPEG_TIMEOUT', '300')))
                outputs.append({'clip_url': f'/api/search/clips/{filename}', 'start': clip_start, 'end': clip_end,
                                'match': selection['match'], 'mode': mode, 'captions_vtt': '\n'.join(vtt_lines)})
        timings = timer.finish()
        note = ''
        if len(outputs) < requested_count:
            note = f'Found {len(outputs)} distinct clip(s). The source duration or spacing of searchable moments does not allow the requested separate clips, even with shorter windows.'
        elif selected and selected[0]['end'] - selected[0]['start'] < clip_length - .01:
            seconds = selected[0]['end'] - selected[0]['start']
            note = f'Used {seconds:g}-second clips instead of the {clip_length}-second target to keep distinct matches without overlap.'
        # Keep the first-clip fields for older standalone clients.
        return {**(outputs[0] if outputs else {}), 'clips': outputs, 'timings': timings, 'selection_note': note}
    except BaseException:
        for output in created:
            output.unlink(missing_ok=True)
        raise
