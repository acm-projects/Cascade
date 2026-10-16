# Research implementation

This package provides the research worker used by the authenticated Cascade app. Start the website from the repository root with `uvicorn app1:app --reload`, not a standalone demo server.

`backend/integration.py` owns the project-scoped `/api/projects/{project_id}/research` and `/api/projects/{project_id}/research-upload` endpoints. It calls the worker functions in `router.py`, which use `pipeline.py` and `youtube_trends.py` for transcription, tags, and comparison against YouTube results. The legacy router object is not mounted as an unauthenticated API.

See [setup](../../docs/setup.md) for dependencies and configuration. Research needs FFmpeg/FFprobe, Whisper, `YOUTUBE_API_KEY`, and `ANTHROPIC_API_KEY`. First use may download models. Analysis can take several minutes. `.cache/` contains reusable provider-derived results; treat it separately from disposable Python caches. Tests mock providers; do not trigger research just to check imports.
