import json
import os
import shutil
import re
import random
import imageio_ffmpeg

# Fix FFmpeg PATH for Whisper and MoviePy on Windows
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
ffmpeg_dir = os.path.dirname(ffmpeg_exe)
os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

expected_ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg.exe")
if not os.path.exists(expected_ffmpeg) and os.path.exists(ffmpeg_exe):
    try:
        shutil.copy(ffmpeg_exe, expected_ffmpeg)
    except Exception:
        pass

import whisper
from moviepy import VideoFileClip, TextClip, CompositeVideoClip

STYLE_PRESETS = {
    "hormozi": {"color": "yellow", "font_size": 48, "pos_y": 0.75},
    "minimalist": {"color": "white", "font_size": 36, "pos_y": 0.85},
    "bold_viral": {"color": "cyan", "font_size": 52, "pos_y": 0.70},
    "cinematic": {"color": "gold", "font_size": 40, "pos_y": 0.80}
}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what", "which",
    "this", "that", "these", "those", "then", "just", "so", "than", "such", "both",
    "through", "about", "for", "is", "of", "while", "during", "to", "from", "in",
    "out", "on", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", 
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", 
    "same", "so", "than", "too", "very", "can", "will", "don't", "should", "now",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "their", "our", "like", "going", "know", "think", "said"
}

HOOK_TEMPLATES = [
    "🚨 THE TRUTH ABOUT {topic} 🚨",
    "🔥 STOP DOING THIS WITH {topic} 🔥",
    "⚡ HOW TO MASTER {topic} 💥",
    "👀 THE SECRET TO {topic} 👀",
    "❓ WHY NOBODY TALKS ABOUT {topic} ❓",
    "⚠️ BIGGEST {topic} MISTAKE ⚠️",
    "🤯 THIS CHANGES {topic} FOREVER 🤯"
]

def generate_catchy_header(clip_text: str, tone: str = "engaging", audience: str = "gen-z") -> str:
    """Generates viral hooks purely offline using local NLP keyword extraction and dynamic templates."""
    clean_text = clip_text.strip()
    if not clean_text:
        return "🔥 WATCH THIS MOMENT! 🔥"

    # Extract words and filter out common filler words to isolate primary topics
    words = [re.sub(r'[^\w]', '', w).upper() for w in clean_text.split()]
    meaningful_words = [w for w in words if w.lower() not in STOP_WORDS and len(w) > 3]

    if meaningful_words:
        # Select the longest/most substantial word as the core subject keyword
        meaningful_words.sort(key=len, reverse=True)
        primary_topic = meaningful_words[0]
        
        # Pick a random high-converting hook pattern
        template = random.choice(HOOK_TEMPLATES)
        return template.format(topic=primary_topic)

    return "🔥 MUST WATCH THIS 🔥"


def generate_four_styled_clips(
    video_url: str = "sample.mp4", 
    styles: list = None, 
    tone: str = "engaging", 
    audience: str = "gen-z"
) -> list:
    input_video_path = "sample.mp4"

    if not os.path.exists(input_video_path):
        raise FileNotFoundError(f"Source video '{input_video_path}' not found.")

    print(f"Loading video '{input_video_path}'...")
    full_video = VideoFileClip(input_video_path)

    if full_video.audio is None:
        raise ValueError("Video does not contain an audio track.")

    print("Transcribing audio locally with Whisper (enabling word timestamps)...")
    model = whisper.load_model("tiny")
    # Enable word_timestamps to obtain word-by-word timing metadata
    transcription = model.transcribe(input_video_path, word_timestamps=True)

    font_path = "C:/Windows/Fonts/arialbd.ttf" if os.path.exists("C:/Windows/Fonts/arialbd.ttf") else "C:/Windows/Fonts/arial.ttf"

    total_duration = full_video.duration
    clip_duration = total_duration / 4.0
    output_filenames = []

    selected_styles = styles if (styles and len(styles) >= 4) else ["hormozi", "minimalist", "bold_viral", "cinematic"]

    for i in range(4):
        style_name = selected_styles[i]
        style_config = STYLE_PRESETS.get(style_name, STYLE_PRESETS["hormozi"])

        start_time = i * clip_duration
        end_time = (i + 1) * clip_duration

        print(f"Rendering Clip {i+1}/4 ({style_name.upper()}) from {start_time:.1f}s to {end_time:.1f}s...")

        sub_video = full_video.subclipped(start_time, end_time)

        clip_transcript_parts = []
        text_clips = []
        
        # Iterate through segments and individual word timestamps
        for segment in transcription.get("segments", []):
            seg_start = segment["start"]
            seg_end = segment["end"]
            
            if seg_start < end_time and seg_end > start_time:
                clip_transcript_parts.append(segment["text"].strip())

                # Word-level animation for punchy, fast captions
                for word_info in segment.get("words", []):
                    w_start = word_info["start"]
                    w_end = word_info["end"]
                    word_text = word_info["word"].strip().upper()

                    if w_start < end_time and w_end > start_time:
                        rel_start = max(0.0, w_start - start_time)
                        rel_end = min(sub_video.duration, w_end - start_time)

                        if rel_end - rel_start <= 0.05 or not word_text:
                            continue

                        txt_clip = (
                            TextClip(
                                text=word_text,
                                font_size=style_config["font_size"],
                                color=style_config["color"],
                                font=font_path,
                                method="caption",
                                size=(int(sub_video.w * 0.80), None)
                            )
                            .with_position(('center', style_config["pos_y"]), relative=True)
                            .with_start(rel_start)
                            .with_duration(rel_end - rel_start)
                        )
                        text_clips.append(txt_clip)

        # Generate creative header offline using keywords
        combined_text = " ".join(clip_transcript_parts)
        header_text = generate_catchy_header(combined_text, tone=tone, audience=audience)

        top_header_clip = (
            TextClip(
                text=header_text,
                font_size=44,
                color="yellow",
                bg_color="black",
                font=font_path,
                method="caption",
                size=(int(sub_video.w * 0.90), None)
            )
            .with_position(('center', 0.08), relative=True)
            .with_start(0)
            .with_duration(sub_video.duration)
        )

        all_overlay_clips = [sub_video, top_header_clip] + text_clips
        final_sub_clip = CompositeVideoClip(all_overlay_clips)
        final_sub_clip = final_sub_clip.with_audio(sub_video.audio)

        output_filename = f"output_clip_{i+1}_{style_name}.mp4"
        final_sub_clip.write_videofile(
            output_filename,
            fps=24,
            codec="libx264",
            audio_codec="aac"
        )
        output_filenames.append(output_filename)

    full_video.close()
    return output_filenames

def generate_subtitled_video():
    generate_four_styled_clips("sample.mp4", ["hormozi", "minimalist", "bold_viral", "cinematic"])

if __name__ == "__main__":
    generate_subtitled_video()