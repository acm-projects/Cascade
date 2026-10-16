import json
import os
import shutil
from pathlib import Path

import imageio_ffmpeg

MODULE_DIR = Path(__file__).resolve().parent

# Fix FFmpeg PATH for Whisper and MoviePy on Windows
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
ffmpeg_dir = os.path.dirname(ffmpeg_exe)
os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

expected_ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg.exe")
if not os.path.exists(expected_ffmpeg) and os.path.exists(ffmpeg_exe):
    try:
        if os.name == "nt":
            shutil.copy(ffmpeg_exe, expected_ffmpeg)
    except Exception:
        pass

import whisper
from moviepy import VideoFileClip, TextClip, CompositeVideoClip

# Map style names to specific aesthetic parameters
STYLE_PRESETS = {
    "hormozi": {"color": "yellow", "font_size": 42, "pos_y": 0.75},
    "minimalist": {"color": "white", "font_size": 32, "pos_y": 0.85},
    "bold_viral": {"color": "cyan", "font_size": 46, "pos_y": 0.70},
    "cinematic": {"color": "gold", "font_size": 36, "pos_y": 0.80}
}

def generate_four_styled_clips(video_path: str, styles: list, tone: str = "engaging", audience: str = "gen-z", output_dir=None, whole_clip=False):
    """
    Main function called by FastAPI background worker in router.py.
    Processes the source video and exports 4 separate clips with distinct styles.
    """
    input_video_path = video_path

    if not os.path.exists(input_video_path):
        raise FileNotFoundError(f"Source video '{input_video_path}' not found.")

    print(f"Loading video '{input_video_path}'...")
    full_video = VideoFileClip(input_video_path)

    try:
        if full_video.audio is None:
            raise ValueError("Video does not contain an audio track.")
    
        print("Transcribing audio with Whisper...")
        model = whisper.load_model("tiny")
        transcription = model.transcribe(input_video_path)
    
        font_path = os.environ.get("CASCADE_CAPTION_FONT") or next((p for p in ["C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if os.path.exists(p)), None)
        destination = Path(output_dir) if output_dir else MODULE_DIR
        destination.mkdir(parents=True, exist_ok=True)
    
        # Divide video duration into 4 equal time blocks
        total_duration = full_video.duration
        clip_duration = total_duration / 4.0
        output_filenames = []
    
        # Ensure at least 4 styles are mapped
        selected_styles = styles if len(styles) >= 4 else ["hormozi", "minimalist", "bold_viral", "cinematic"]
    
        for i in range(4):
            style_name = selected_styles[i]
            style_config = STYLE_PRESETS.get(style_name, STYLE_PRESETS["hormozi"])
    
            start_time = 0 if whole_clip else i * clip_duration
            end_time = total_duration if whole_clip else (i + 1) * clip_duration
    
            print(f"Rendering Clip {i+1}/4 ({style_name.upper()}) from {start_time:.1f}s to {end_time:.1f}s...")
    
            # Subclip the video segment
            sub_video = full_video.subclipped(start_time, end_time)
    
            # Filter transcript segments that belong inside this time block
            text_clips = []
            for segment in transcription.get("segments", []):
                seg_start = segment["start"]
                seg_end = segment["end"]
                
                if seg_end > start_time and seg_start < end_time:
                    rel_start = max(seg_start, start_time) - start_time
                    rel_end = min(seg_end, end_time) - start_time
                    text = segment["text"].strip()
    
                    txt_clip = (
                        TextClip(
                            text=text,
                            font_size=style_config["font_size"],
                            color=style_config["color"],
                            font=font_path,
                            method="caption",
                            size=(int(sub_video.w * 0.85), None)
                        )
                        .with_position(('center', style_config["pos_y"]), relative=True)
                        .with_start(rel_start)
                        .with_duration(rel_end - rel_start)
                    )
                    text_clips.append(txt_clip)
    
            # Composite clip and reattach subclip audio
            final_sub_clip = CompositeVideoClip([sub_video] + text_clips)
            final_sub_clip = final_sub_clip.with_audio(sub_video.audio)
    
            output_filename = f"output_clip_{i+1}_{style_name}.mp4"
            output_path = str(destination / output_filename)
            final_sub_clip.write_videofile(
                output_path,
                fps=24,
                codec="libx264",
                audio_codec="aac"
            )
            def vtt_time(seconds):
                ms = round(seconds * 1000)
                hours, ms = divmod(ms, 3600000)
                minutes, ms = divmod(ms, 60000)
                secs, ms = divmod(ms, 1000)
                return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"
            captions = ["WEBVTT\n"]
            for segment in transcription.get("segments", []):
                start = max(segment["start"], start_time)
                end = min(segment["end"], end_time)
                if end > start:
                    captions.append(f"{vtt_time(start-start_time)} --> {vtt_time(end-start_time)}\n{segment['text'].strip()}\n")
            (destination / output_filename).with_suffix(".vtt").write_text("\n".join(captions), encoding="utf-8")
            output_filenames.append(output_filename)
            final_sub_clip.close()
            for text_clip in text_clips:
                text_clip.close()
    
        return output_filenames
    finally:
        full_video.close()
