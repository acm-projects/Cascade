# Setup and runtime

Run all commands from the repository root. Use Python 3.11 or newer and a virtual environment, then install `requirements.txt` (which includes `backend/requirements.txt`). Install FFmpeg and FFprobe through your system package manager. Caption exports need a build with libass/subtitles support; Homebrew users can install `ffmpeg-full`.

Copy `.env.example` to `.env` only for a new setup. Never overwrite an existing configuration. The server loads the root `.env`; keys stay on the server. Start with:

```sh
uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. `backend.app:app` remains an alternate import alias. Pages and assets are served from a whitelist in `app1.py`; moving them into `web/` does not change their public URLs. Do not expose the repository as a public static directory.

## Authentication and storage

Configure `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, and `CLERK_AUTHORIZED_PARTIES` for the local origins you use. The consolidated `web/index.html` template retains the original publishable-key fallback when no environment key is set; root `login.html` is superseded. Only the selected view is rendered, and the fallback template declaration is not emitted into the page. Production requests still require Clerk authentication and ownership checks.

`CASCADE_STORAGE=local` keeps media locally. `auto` selects S3 when configured; `s3` requires `S3_BUCKET_NAME`, region and AWS credentials. Existing local source files are needed for editing and exports even when generated delivery uses S3. Preserve the complete `video_jobs/` directory: it includes uploads, transcripts, results, owner metadata, projects, settings and editor drafts. Project/editor persistence is owner-scoped atomic JSON; cleanup introduced no schema migration. Do not delete root JSON records or `outputs/` simply because they are outside the active jobs directory.

## Generation, research and export

OpenAI scene generation and editor chat use `OPENAI_API_KEY`. `OPENAI_SCENE_MODEL` defaults to the existing scene model; `OPENAI_EDITOR_MODEL` optionally overrides chat. Missing credentials or provider failures are reported by the application. Never send keys to the browser.

Local visual generation uses Ollama (`CASCADE_MODEL`, default `qwen3-vl:4b-instruct`); local speech/search requires Whisper and sentence-transformer dependencies and may download models on first use. Research uses `ANTHROPIC_API_KEY` and `YOUTUBE_API_KEY`; `ANTHROPIC_CALLS_DISABLED=true` prevents paid Anthropic calls. Normal generation yields up to the qualifying candidate limit, not guaranteed duplicate-filled results. See the investigation document for the implemented multi-clip fix and its verification limits.

`CASCADE_FFMPEG` and `CASCADE_EDITOR_FFMPEG` can select compatible FFmpeg binaries. Editor downloads render locally on demand using saved trim, composition and captions. The editor preview performs ordinary edits locally without generating an MP4. Keep both `backend/clips/render_subtitles.py` and `backend/video_tools.py`: they provide distinct active caption/export capabilities.

## Checks

See the root README for offline tests and `editor.md` for isolated Chrome playback/export checks. `tests/manual/` contains explicit opt-in smoke scripts; `live_openai_smoke.py` can incur provider charges and is not an automated regression check. Browser fixtures use temporary storage and mocked identity/providers, while playback and media encoding are real. Live authentication, cloud delivery and paid generation require separately configured integration checks.

Pexels stock footage uses the server-only `PEXELS_API_KEY` from the root `.env`. Restart the API after changing it. See [B-roll setup and workflow](broll.md).
