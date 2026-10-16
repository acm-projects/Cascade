"""Find four relevant moments in a video and export captioned clips."""

from pathlib import Path

import whisper
from moviepy import CompositeVideoClip, TextClip, VideoFileClip
from sentence_transformers import SentenceTransformer, util


STYLE_PRESETS = {
    "hormozi": {"color": "yellow", "font_size": 42, "pos_y": 0.75},
    "minimalist": {"color": "white", "font_size": 32, "pos_y": 0.85},
    "bold_viral": {"color": "cyan", "font_size": 46, "pos_y": 0.70},
    "cinematic": {"color": "gold", "font_size": 36, "pos_y": 0.80},
}


def find_top_timestamps(user_query, chunks, top_k=4):
    if not chunks:
        return []
    model = SentenceTransformer("all-MiniLM-L6-v2")
    query_vector = model.encode(user_query, convert_to_tensor=True)
    chunk_vectors = model.encode([c["text"] for c in chunks], convert_to_tensor=True)
    scores = util.cos_sim(query_vector, chunk_vectors)[0]
    indices = scores.argsort(descending=True)[:top_k]
    return [chunks[int(index)] for index in indices]


def generate_four_styled_clips(
    video_path: str,
    query: str,
    styles=None,
    output_dir="outputs",
    clip_duration=20.0,
):
    """Search the video's speech, then render up to four matching clips."""
    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(f"Video not found: {source}")
    if not query.strip():
        raise ValueError("Enter something to search for.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    style_names = styles or list(STYLE_PRESETS)
    if len(style_names) < 4:
        raise ValueError("Provide four style names.")

    speech_model = whisper.load_model("tiny")
    segments = speech_model.transcribe(str(source))["segments"]
    matches = find_top_timestamps(query, segments)
    if not matches:
        raise ValueError("No speech was found in this video.")

    outputs = []
    with VideoFileClip(str(source)) as video:
        for i, match in enumerate(matches):
            style_name = style_names[i]
            if style_name not in STYLE_PRESETS:
                raise ValueError(f"Unknown style: {style_name}")
            style = STYLE_PRESETS[style_name]
            start = max(0.0, min(float(match["start"]), video.duration - 0.01))
            end = min(video.duration, start + clip_duration)
            if end <= start:
                continue

            sub_video = video.subclipped(start, end)
            captions = []
            for segment in segments:
                caption_start = max(start, float(segment["start"]))
                caption_end = min(end, float(segment["end"]))
                if caption_end <= caption_start or not segment["text"].strip():
                    continue
                caption = (
                    TextClip(
                        text=segment["text"].strip(),
                        font_size=style["font_size"],
                        color=style["color"],
                        method="caption",
                        size=(int(sub_video.w * 0.85), None),
                    )
                    .with_position(("center", style["pos_y"]), relative=True)
                    .with_start(caption_start - start)
                    .with_duration(caption_end - caption_start)
                )
                captions.append(caption)

            final = CompositeVideoClip([sub_video, *captions]).with_audio(sub_video.audio)
            destination = output_path / f"output_clip_{i + 1}_{style_name}.mp4"
            try:
                final.write_videofile(
                    str(destination), codec="libx264", audio_codec="aac", logger=None
                )
                outputs.append(str(destination))
            finally:
                final.close()
                for caption in captions:
                    caption.close()
                sub_video.close()

    return outputs


if __name__ == "__main__":
    for filename in generate_four_styled_clips("sample.mp4", "old key clock tower"):
        print(filename)