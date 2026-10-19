# Research implementation

The authenticated project research routes in `backend/integration.py` use this package to compare uploaded video against YouTube trends. Main's Deepgram transcription and configurable `LLM_PROVIDER` tagging remain in place. Start the website from the repository root with `uvicorn app1:app --reload`.

Research needs FFmpeg/FFprobe, `DEEPGRAM_API_KEY`, `YOUTUBE_API_KEY`, and the API key for the configured LLM provider. Provider-derived `.cache/` data is reusable; tests mock external providers. The legacy router module remains available but is not mounted as an unauthenticated website API.
