import json
import os
import shutil
import re
import random
from pathlib import Path
import imageio_ffmpeg

# Fix FFmpeg PATH for Windows execution
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
from sentence_transformers import SentenceTransformer, util

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

    words = [re.sub(r'[^\w]', '', w).upper() for w in clean_text.split()]
    meaningful_words = [w for w in words if w.lower() not in STOP_WORDS and len(w) > 3]

    if meaningful_words:
        meaningful_words.sort(key=len, reverse=True)
        primary_topic = meaningful_words[0]
        template = random.choice(HOOK_TEMPLATES)
        return template.format(topic=primary_topic)

    return "🔥 MUST WATCH THIS 🔥"


def generate_four_styled_clips(
    video_path: str = "sample.mp4", 
    query: str = None, 
    output_dir: str = ".", 
    styles: list = None,
    tone: str = "engaging",
    audience: str = "gen-z"
) -> list:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(video_path):
        video_path = "sample.mp4"

    font_path = "C:/Windows/Fonts/arialbd.ttf" if os.path.exists("C:/Windows/Fonts/arialbd.ttf") else "C:/Windows/Fonts/arial.ttf"

    print("Transcribing audio locally with Whisper (enabling word timestamps)...")
    model = whisper.load_model("tiny")
    transcription = model.transcribe(video_path, word_timestamps=True)

    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"]}
        for s in transcription.get("segments", [])
        if s["text"].strip()
    ]

    selected_matches = []

    # If a semantic query is passed, search for top matching segments
    if query and len(segments) >= 4:
        search_model = SentenceTransformer("all-MiniLM-L6-v2")
        query_vector = search_model.encode(query, convert_to_tensor=True)
        segment_vectors = search_model.encode(
            [segment["text"] for segment in segments],
            convert_to_tensor=True,
        )
        scores = util.cos_sim(query_vector, segment_vectors)[0]
        best_indices = scores.argsort(descending=True)[:4]
        selected_matches = [segments[int(index)] for index in best_indices]

    selected_styles = styles if (styles and len(styles) >= 4) else ["hormozi", "minimalist", "bold_viral", "cinematic"]
    filenames = []

    with VideoFileClip(video_path) as full_video:
        if full_video.audio is None:
            raise ValueError("The video has no audio track.")

        total_duration = full_video.duration
        clip_duration = total_duration / 4.0

        for i in range(4):
            style_name = selected_styles[i]
            style_config = STYLE_PRESETS.get(style_name, STYLE_PRESETS["hormozi"])

            if selected_matches:
                match = selected_matches[i]
                start_time = max(0.0, float(match["start"]) - 2.0)
                end_time = min(total_duration, start_time + 20.0)
                start_time = max(0.0, end_time - 20.0)
            else:
                start_time = i * clip_duration
                end_time = (i + 1) * clip_duration

            sub_video = full_video.subclipped(start_time, end_time)

            clip_transcript_parts = []
            text_clips = []

            # Word-level caption generation loop
            for segment in transcription.get("segments", []):
                seg_start = segment["start"]
                seg_end = segment["end"]

                if seg_start < end_time and seg_end > start_time:
                    clip_transcript_parts.append(segment["text"].strip())

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

            # Generate top hook header using NLP extraction
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
            finished = CompositeVideoClip(all_overlay_clips).with_audio(sub_video.audio)

            filename = output / f"clip_{i+1}_{style_name}.mp4"

            try:
                finished.write_videofile(
                    str(filename),
                    fps=24,
                    codec="libx264",
                    audio_codec="aac",
                )
                filenames.append(str(filename))
            finally:
                finished.close()
                for t in text_clips:
                    t.close()
                top_header_clip.close()

    return filenames


def generate_subtitled_video():
    generate_four_styled_clips("sample.mp4", styles=["hormozi", "minimalist", "bold_viral", "cinematic"])


if __name__ == "__main__":
    generate_subtitled_video()