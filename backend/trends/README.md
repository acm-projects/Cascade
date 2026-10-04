# Video Trend Analysis Demo

A demo full-stack tool: upload a video, give it a topic, and it compares your
video's style/content tags against the top 5 trending YouTube videos for that
topic, using ffmpeg + Whisper for transcription/frames and Claude for tagging.

## Prerequisites

### ffmpeg

- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **Windows**: download a build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or
  `winget install ffmpeg`, then make sure `ffmpeg` and `ffprobe` are on your `PATH`.

Verify with:

```bash
ffmpeg -version
```

### API keys

**YouTube Data API v3 key**
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create (or select) a project, then enable "YouTube Data API v3" under APIs & Services.
3. Go to Credentials -> Create Credentials -> API key.
4. Copy the key into `YOUTUBE_API_KEY` in your `.env`.

**Anthropic API key**
1. Go to the [Anthropic Console](https://console.anthropic.com/settings/keys).
2. Create a new API key.
3. Copy it into `ANTHROPIC_API_KEY` in your `.env`.

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then fill in your keys
```

## Running locally

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser. The frontend
is served as a static file by the same FastAPI app, and calls `/api/analyze`
on the same origin.

Analysis typically takes **1-3 minutes** per request (downloading and processing
5 trending videos plus your upload) — this is expected for a demo, not a bug.

## Notes

This is a demo, not hardened for production use: no auth, no rate limiting, no
persistence (results are computed per-request and not saved).
