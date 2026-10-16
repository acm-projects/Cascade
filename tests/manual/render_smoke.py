"""Optional real MoviePy/FFmpeg render smoke test; transcription is mocked.
Run from the repo root: python tests/manual/render_smoke.py
Uses only synthetic media in a temporary folder; no AI or storage API calls.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.clips.render_subtitles import generate_four_styled_clips

class Transcript:
    def transcribe(self, *args):
        return {"segments": [{"start": 0, "end": 2, "text": "Caption render smoke test"}]}

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    source = folder / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=24:d=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source)], check=True)
    with patch("backend.clips.render_subtitles.whisper.load_model", return_value=Transcript()):
        names = generate_four_styled_clips(str(source), ["hormozi", "minimalist", "bold_viral", "cinematic"], output_dir=folder / "rendered", whole_clip=True)
    assert len(names) == 4
    for name in names:
        video = folder / "rendered" / name
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]))
        assert float(probe["format"]["duration"]) > 1.9
        assert {stream["codec_type"] for stream in probe["streams"]} >= {"audio", "video"}
        captions = video.with_suffix(".vtt").read_text()
        assert "WEBVTT" in captions and "Caption render smoke test" in captions
    print("PASS: four real captioned MP4s with audio and matching VTT; synthetic video, mocked transcription.")
