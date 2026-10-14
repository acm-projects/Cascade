from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
import shutil
import subprocess
import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel
from PIL import Image
from sentence_transformers import SentenceTransformer
from pipeline_timing import StageTimer

router = APIRouter()

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUTS = PROJECT_DIR / "outputs"
OUTPUTS.mkdir(exist_ok=True)

whisper_model = search_model = visual_model = None

def load_models(mode, progress=lambda message: None):
    global whisper_model, search_model, visual_model
    if mode in ('speech', 'captions') and whisper_model is None:
        progress('Loading speech model (first use may download model files)...')
        whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    if mode == "speech" and search_model is None:
        progress('Loading speech search model (first use may download model files)...')
        search_model = SentenceTransformer("all-MiniLM-L6-v2")
    if mode == "visual" and visual_model is None:
        progress('Loading visual search model (first use may download model files)...')
        visual_model = SentenceTransformer("sentence-transformers/clip-ViT-B-32")


# Note: the standalone "/" page is now served via StaticFiles at /search-ui
# (see backend/app.py) instead of a dedicated route here, since this router
# is mounted under /api/search alongside the other features' APIs.


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


def search_video(video, search, mode, clip_length, progress=lambda message: None, timing=lambda timings, active: None):
    timer = StageTimer(timing)
    if not search.strip():
        raise HTTPException(status_code=400, detail="Type what you want to find.")

    if mode not in ("speech", "visual"):
        raise HTTPException(status_code=400, detail="Mode must be speech or visual.")

    if clip_length not in (15, 30, 60):
        raise HTTPException(
            status_code=400,
            detail="Choose 15, 30, or 60 seconds.",
        )

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise HTTPException(
            status_code=500,
            detail="FFmpeg and ffprobe must be installed.",
        )

    progress('Loading search models...')
    timer.start('Search model loading')
    load_models(mode, progress)
    timer.start('Video preparation')

    with TemporaryDirectory() as folder:
        work_dir = Path(folder)
        suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
        video_path = work_dir / f"uploaded{suffix}"

        with video_path.open("wb") as destination:
            shutil.copyfileobj(video.file, destination)

        try:
            duration = get_duration(video_path)
        except (subprocess.CalledProcessError, ValueError, KeyError):
            raise HTTPException(
                status_code=400,
                detail="Could not read this video's duration.",
            )

        if mode == "speech":
            timer.start('Whisper transcription')
            progress('Transcribing video for speech search...')
            segments, _ = whisper_model.transcribe(str(video_path))
            transcript = [
                {"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segments
                if s.text.strip()
            ]

            if not transcript:
                raise HTTPException(
                    status_code=400,
                    detail="Whisper could not find speech in this video.",
                )

            sentences = [part["text"] for part in transcript]
            timer.start('Text embeddings')
            embeddings = search_model.encode(sentences)
            query_embedding = search_model.encode(search)
            timer.start('Match selection')
            scores = search_model.similarity(query_embedding, embeddings)

            best_index = scores.argmax().item()
            match = transcript[best_index]

            clip_start = max(0, match["start"] - 3)
            clip_end = min(duration, clip_start + clip_length)
            match_text = match["text"]

        else:
            # Bound inference cost while sampling the entire video, not only its first five minutes.
            sample_interval = max(3.0, duration / 100)
            timer.start('Frame extraction')
            progress('Extracting up to 100 preview frames across the video...')
            frames_dir = work_dir / "frames"
            frames_dir.mkdir()

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i", str(video_path),
                        "-vf", (f"fps=1/{sample_interval}," if duration >= sample_interval else '') + "scale=320:-2",
                        "-frames:v", "100" if duration >= sample_interval else "1",
                        str(frames_dir / "frame_%04d.jpg"),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except subprocess.CalledProcessError as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Could not extract frames: {error.stderr[-500:]}",
                )

            frame_paths = sorted(frames_dir.glob("frame_*.jpg"))
            if not frame_paths:
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video_path), '-frames:v', '1',
                                '-vf', 'scale=320:-2', str(frames_dir / 'frame_0001.jpg')],
                               check=True, capture_output=True, timeout=60)
                frame_paths = sorted(frames_dir.glob('frame_*.jpg'))

            timer.start('Image decoding')
            images = []
            for path in frame_paths:
                with Image.open(path) as image:
                    images.append(image.convert("RGB"))

            progress(f'Comparing your prompt with {len(images)} video frames...')
            timer.start('Prompt embedding')
            query_embedding = visual_model.encode(
                search, normalize_embeddings=True
            )
            timer.start('Image embeddings')
            embeddings = []
            for offset in range(0, len(images), 8):
                progress(f'Comparing video frames {offset + 1}–{min(offset + 8, len(images))}/{len(images)}...')
                embeddings.extend(visual_model.encode(images[offset:offset + 8], normalize_embeddings=True))
            import numpy as np
            frame_embeddings = np.asarray(embeddings)
            for image in images:
                image.close()
            timer.start('Match selection')
            scores = frame_embeddings @ query_embedding
            best_index = int(scores.argmax())

            matched_second = min(duration, (best_index + 0.5) * sample_interval) if duration >= sample_interval else 0
            clip_start = max(0, matched_second - 5)
            clip_end = min(duration, clip_start + clip_length)
            match_text = f"Best visual match near {matched_second} seconds"

            # Caption only the selected window, rather than transcribing the whole source.
            audio_path = work_dir / 'selected.wav'
            timer.start('Audio inspection')
            probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                                    '-show_entries', 'stream=index', '-of', 'csv=p=0', str(video_path)],
                                   check=True, capture_output=True, text=True, timeout=30)
            transcript = []
            if probe.stdout.strip():
                timer.start('Whisper model loading')
                load_models('captions', progress)
                timer.start('Audio extraction')
                progress('Transcribing only the selected clip for captions...')
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(clip_start), '-i', str(video_path),
                                '-t', str(clip_end - clip_start), '-vn', '-ac', '1', '-ar', '16000', str(audio_path)],
                               check=True, capture_output=True, timeout=120)
                timer.start('Whisper transcription')
                segments, _ = whisper_model.transcribe(str(audio_path), beam_size=1, vad_filter=True)
                transcript = [{"start": s.start + clip_start, "end": s.end + clip_start, "text": s.text.strip()}
                              for s in segments if s.text.strip()]

        # Keep only speech inside the selected clip. Adjust timestamps so
        # the captions start at 0 seconds in the new video.
        timer.start('Caption preparation')
        subtitle_lines = []
        vtt_lines = ["WEBVTT\n"]
        for part in transcript:
            start = max(part["start"], clip_start)
            end = min(part["end"], clip_end)

            if end <= start:
                continue

            vtt_lines.append(f"{srt_time(start-clip_start).replace(chr(44), chr(46))} --> {srt_time(end-clip_start).replace(chr(44), chr(46))}\n{part['text']}\n")
            subtitle_lines.append(
                f"{len(subtitle_lines) + 1}\n"
                f"{srt_time(start - clip_start)} --> "
                f"{srt_time(end - clip_start)}\n"
                f"{part['text']}\n"
            )

        if subtitle_lines:
            (work_dir / "captions.srt").write_text(
                "\n".join(subtitle_lines),
                encoding="utf-8",
            )

        filename = f"{uuid4().hex}.mp4"
        output_path = OUTPUTS / filename

        command = [
            "ffmpeg",
            "-y",
            "-ss", str(clip_start),
            "-i", str(video_path),
            "-t", str(clip_end - clip_start),
        ]

        # Burn subtitles onto the video if Whisper found speech.
        if subtitle_lines:
            command += ["-vf", "subtitles=filename=captions.srt"]

        command += [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(output_path),
        ]

        try:
            timer.start('Video rendering')
            progress('Rendering the selected clip and captions...')
            subprocess.run(
                command,
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=float(os.getenv('CASCADE_FFMPEG_TIMEOUT', '300')),
            )
        except subprocess.CalledProcessError as error:
            raise HTTPException(
                status_code=500,
                detail=f"Could not make clip: {error.stderr[-500:]}",
            )

    timings = timer.finish()
    return {
        'timings': timings,
        "captions_vtt": "\n".join(vtt_lines),
        "clip_url": f"/api/search/clips/{filename}",
        "start": round(clip_start, 1),
        "end": round(clip_end, 1),
        "match": match_text,
        "mode": mode,
    }
