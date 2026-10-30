# Setup and runtime

Run all commands from the repository root. Use Python 3.11 or newer and a virtual environment, then install `requirements.txt` (which includes `backend/requirements.txt`). Install FFmpeg and FFprobe through your system package manager. Caption exports need a build with libass/subtitles support; Homebrew users can install `ffmpeg-full`.

Copy `.env.example` to `.env` only for a new setup. Never overwrite an existing configuration. The server loads the root `.env`; keys stay on the server. Start with:

```sh
uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. `app1:app` is the application entry point. Pages and assets are served from a whitelist in `app1.py`; moving them into `web/` does not change their public URLs. Do not expose the repository as a public static directory.

## Authentication and storage

Configure `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, and `CLERK_AUTHORIZED_PARTIES` for the local origins you use. The consolidated `web/index.html` template retains the original publishable-key fallback when no environment key is set; root `login.html` is superseded. Only the selected view is rendered, and the fallback template declaration is not emitted into the page. Production requests still require Clerk authentication and ownership checks.

`CASCADE_STORAGE=local` keeps media locally. `auto` selects S3 when configured; `s3` requires `S3_BUCKET_NAME`, region and AWS credentials. Existing local source files are needed for editing and exports even when generated delivery uses S3. Preserve the complete `video_jobs/` directory: it includes uploads, transcripts, results, owner metadata, projects, settings and editor drafts. Project/editor persistence is owner-scoped atomic JSON; cleanup introduced no schema migration. Do not delete root JSON records or `outputs/` simply because they are outside the active jobs directory.

## Generation, research and export

Clip generation preserves main’s agent pipeline: `DEEPGRAM_API_KEY` supplies transcription, and `LLM_PROVIDER=anthropic|openai` selects the generation, summaries and research provider. Set that provider’s key (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`). Model choices remain those in `backend/cascade_llm/clients.py`. Missing credentials fail early at upload. CLIP/MiniLM embeddings can load at startup; `CASCADE_WARM_MODELS=0` disables warming.

Editor chat uses the same `backend/cascade_llm` structured-output layer as generation,
and follows `LLM_PROVIDER=anthropic|openai`. Only the selected provider's key is required.
Optional `CASCADE_EDITOR_PROVIDER=anthropic|openai` overrides chat's provider per call,
without changing generation or concurrent requests. Model choices stay in
`backend/cascade_llm/clients.py`; the old `OPENAI_EDITOR_MODEL` override is no longer
used by editor chat. Missing credentials return 503; malformed AI responses return
502 without applying edits. Proposal validation and allowed actions are unchanged.
The older scene helper remains for compatibility, not as the website's generation
engine. Historical `openai`/`qwen` generation requests use the current agent. Direct
speech/visual workers retain Deepgram transcription and requested-count/follow-up
handling. Research also needs `YOUTUBE_API_KEY`.

Generation groups, requested counts (1–12), source reuse, parent-context expansion, retries and deletion remain owner-scoped. The agent retains its default four-clip behavior, with per-request limits for other counts. No duplicate clips are created to fill unavailable results. Pexels B-roll is available in the editor through its B-roll tab and validated chat actions; it does not change the generation pipeline.

`CASCADE_FFMPEG` and `CASCADE_EDITOR_FFMPEG` can select compatible FFmpeg binaries. Editor downloads render locally on demand using saved trim, composition and captions. The editor preview performs ordinary edits locally without generating an MP4. Keep both `backend/clips/render_subtitles.py` and `backend/video_tools.py`: they provide distinct active caption/export capabilities.

## Checks

See the root README for offline tests and `editor.md` for isolated Chrome playback/export checks. `tests/manual/` contains explicit opt-in smoke scripts; `live_openai_smoke.py` can incur provider charges and is not an automated regression check. Browser fixtures use temporary storage and mocked identity/providers, while playback and media encoding are real. Live authentication, cloud delivery and paid generation require separately configured integration checks.

Pexels stock footage uses the server-only `PEXELS_API_KEY` from the root `.env`. Restart the API after changing it. See [B-roll setup and workflow](broll.md).
