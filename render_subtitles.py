from pathlib import Path

from faster_whisper import WhisperModel
from moviepy import VideoFileClip, TextClip, CompositeVideoClip
from sentence_transformers import SentenceTransformer, util


STYLES = {
    "hormozi": {"color": "yellow", "font_size": 42, "y": 0.75},
    "minimalist": {"color": "white", "font_size": 32, "y": 0.85},
    "bold_viral": {"color": "cyan", "font_size": 46, "y": 0.70},
    "cinematic": {"color": "gold", "font_size": 36, "y": 0.80},
}


def generate_four_styled_clips(video_path: str, query: str, output_dir: str):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # Transcribe the uploaded video.
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    result, _ = model.transcribe(video_path)
    segments = [
        {"start": s.start, "end": s.end, "text": s.text}
        for s in result
        if s.text.strip()
    ]
    
    if len(segments) < 4:
        raise ValueError("The video needs at least four spoken segments.")

    # Find the four spoken moments closest to the search phrase.
    search_model = SentenceTransformer("all-MiniLM-L6-v2")
    query_vector = search_model.encode(query, convert_to_tensor=True)
    segment_vectors = search_model.encode(
        [segment["text"] for segment in segments],
        convert_to_tensor=True,
    )
    scores = util.cos_sim(query_vector, segment_vectors)[0]
    best_indices = scores.argsort(descending=True)[:4]
    matches = [segments[int(index)] for index in best_indices]

    filenames = []

    with VideoFileClip(video_path) as video:
        if video.audio is None:
            raise ValueError("The video has no audio track.")

        for number, (match, style_name) in enumerate(
            zip(matches, STYLES), start=1
        ):
            style = STYLES[style_name]

            start = max(0.0, float(match["start"]) - 3.0)
            end = min(video.duration, start + 20.0)
            start = max(0.0, end - 20.0)
            sub_video = video.subclipped(start, end)

            captions = []
            for segment in segments:
                caption_start = max(start, float(segment["start"]))
                caption_end = min(end, float(segment["end"]))

                if caption_end <= caption_start:
                    continue

                caption = (
                    TextClip(
                        text=segment["text"].strip(),
                        font_size=style["font_size"],
                        color=style["color"],
                        method="caption",
                        size=(int(sub_video.w * 0.85), None),
                    )
                    .with_position(("center", style["y"]), relative=True)
                    .with_start(caption_start - start)
                    .with_duration(caption_end - caption_start)
                )
                captions.append(caption)

            finished = CompositeVideoClip(
                [sub_video, *captions]
            ).with_audio(sub_video.audio)

            filename = output / f"clip_{number}_{style_name}.mp4"

            try:
                finished.write_videofile(
                    str(filename),
                    codec="libx264",
                    audio_codec="aac",
                )
                filenames.append(str(filename))
            finally:
                finished.close()
                for caption in captions:
                    caption.close()
                sub_video.close()

    return filenames