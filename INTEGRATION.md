# Cascade integration

Branch: `cascade/integration`, based on `cascade/new-website` at `1740bd8b276c799a99a38a62e30a30e72c5729f2`.
Backend source: fetched `origin/main` at `49c529b249fbd044f85e5bfb6eb84b47b0d6621c`.
Local `main` was different and was not used as the backend source.

## What is connected

The updated `_C.html` pages, shared CSS, and existing `flow_C.js` remain the active website. The old React frontend from main is an empty scaffold and was not substituted for this design. `app_C.js` is a separate, unused simulation prototype and is preserved unchanged; it is not served by the integration app.

- Existing Clerk sign-in, verified sessions, account name, and sign-out are retained. Profile opens Clerk's actual profile interface.
- Projects are created through the authenticated backend, appear as tiles, and reopen by ID. Names, upload history, prompts, source videos, generated clips, research results, and saved clip references persist on the server.
- Every new upload is attached to a verified user and project. Opening a project restores a saved source video and allows another prompt without selecting the file again.
- Existing Ollama/Qwen prompt search is retained and can now return up to four real non-overlapping matches. Speech and visual search from `origin/main` are selectable alternatives.
- The canvas displays actual generated videos and lets you select which clip opens in the editor. The editor can switch between available clips.
- Clip generation uses real job status and errors. Interrupted jobs explicitly fail after a server restart; completed jobs and saved research remain readable.
- Existing S3 upload and protected clip/caption delivery remain in use. Caption style and search results use the same ownership and storage contract.
- Caption rendering from `origin/main` renders the selected clip in four styles. Its font handling now supports macOS/Linux, its files are isolated per job, and it writes matching VTT captions. Rendering the whole selected clip is intentional; the legacy standalone renderer divided the original input into quarters.
- Trend research from `origin/main` compares the original upload with current YouTube videos using Whisper and Anthropic. Results are saved and restored in the editor.
- Save Clip persists an actual job/clip reference, rather than claiming an edited video has been rendered. Exports displays selected/saved real clips, downloads the existing MP4, and downloads actual VTT captions. Speech/visual search and caption styles also burn captions into the MP4.
- Previous user-owned clips without a project association remain downloadable from **Previous generated clips** on the projects page. Their ownership files and media are not migrated or overwritten.

## Storage and configuration

No SQL/Neon database code exists in either inspected branch. No database configuration was replaced and no SQL migration is required. This is an additive local-filesystem implementation using the website backend's existing `video_jobs` directory, not a claim of Neon integration.

New projects live at `video_jobs/projects/<SHA256-of-user-ID>/<project-ID>.json`. Job ownership records for new uploads additionally include `project_id`, `prompt`, and `source_name`. Saved clip references live in the project record. Existing job directories are left intact. Back up `video_jobs` and retain it across service restarts/deployments; S3 holds generated media, but does not hold the project index or original uploads. There is no multi-process database locking: run one Uvicorn worker on one persistent filesystem.

Existing `.env`, Clerk validation/configuration, AWS credential resolution, S3 bucket/region, and root preferences files remain unchanged. No secrets are included in the integration files. Do not commit `.env`, runtime records, or generated media.

`backend/` contains feature source copied from fetched `origin/main`. `backend/app.py` delegates to the authenticated website app. The old standalone search/clip/trend routers and diagnostic HTML are not mounted publicly; `integration.py` calls their processing functionality behind Clerk and ownership checks. The legacy `/settings` form source is retained but is not mounted: its shared global preferences storage is not a per-user settings implementation.

## Unfinished behavior

Free-form editing chat, editable caption text/fonts/colors/placement, timeline edits, aspect ratio/cropping, subject tracking, B-roll uploads/generation/compositing, merged multi-clip sequences, format/resolution conversion, and direct social publishing have no integrated implementation. Those existing controls stay disabled or explicitly labeled unfinished. Selecting clips opens one selected clip at a time, rather than assembling a multi-clip sequence. The four caption treatments are rendered presets; tone/audience inputs in the old renderer do not affect rendering.

There is no cross-device source upload storage, automatic interrupted-job retry, or project database synchronization. The browser reloads the saved source as a Blob/File, so opening a large project downloads its source into browser memory. Clip playback/download also retains the existing authenticated Blob approach.

## Install and run

Use Python 3.12, FFmpeg/ffprobe, and Ollama. From the repository root on macOS:

```bash
brew install python@3.12 ffmpeg ollama
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If those tools are already installed, skip the Homebrew command. Node is only needed for the JavaScript syntax check; the website has no Node build step.

Keep your existing `.env` and AWS credentials. Configure the following locally if not already set; do not overwrite a working file:

- `CLERK_PUBLISHABLE_KEY` (the existing `login.html` fallback is retained).
- `CLERK_SECRET_KEY` for account lookup.
- `CLERK_AUTHORIZED_PARTIES=http://127.0.0.1:8000,http://localhost:8000`, or retain your existing allowed origins and use a matching host/port in the browser.
- `S3_BUCKET_NAME`, `AWS_DEFAULT_REGION` (default `us-east-2`), and AWS credentials through your existing AWS configuration or environment. The existing account-specific S3 prefix remains unchanged. The identity needs access to upload/read generated clips and captions.
- Research only: `YOUTUBE_API_KEY` with YouTube Data API v3 enabled, and `ANTHROPIC_API_KEY`. `ANTHROPIC_CALLS_DISABLED=true` preserves the existing research kill switch; uncached research fails explicitly while it is enabled.
- Optional: `CASCADE_CAPTION_FONT` set to an existing font file if automatic OS font discovery is unsuitable.

Start Ollama in one terminal (unless its service is already running):

```bash
ollama serve
```

In a second terminal:

```bash
ollama pull qwen3-vl:4b-instruct
source .venv/bin/activate
python -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**. The same service serves both the website and APIs. Do not use `python -m http.server`, open the HTML with `file://`, or start the old Flask/standalone apps. `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000` is an equivalent entrypoint from the repository root.

Whisper and SentenceTransformer models download on first use. Qwen search requires Ollama; speech/visual search do not require Ollama but still require their model downloads, FFmpeg, and the existing S3 configuration. Research requires Internet access, YouTube downloads/API, and Anthropic; it can incur API charges. Caption presets require an audio track and Whisper's tiny model.

For development, you may add `--reload`, but do not edit/restart the server during processing; queued/running jobs are in-process and will be interrupted.

## Checks and manual verification

Run:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall -q app1.py integration.py backend tests
node --check flow_C.js
python tests/render_smoke.py
```

Passed in the implementation environment:

- Seven HTTP/persistence/ownership/selection tests. Identity verification and worker/provider calls are mocked for these contract tests; this does not certify live Clerk, S3, or AI services.
- Python compilation and JavaScript syntax checks.
- Four actual MoviePy/FFmpeg MP4 renders with audio, matching VTT output, and FFprobe verification, using synthetic media and mocked Whisper transcription.
- Static homepage serving and unauthenticated API rejection.

Not exercised: live Clerk sign-in/profile/sign-out, AWS/S3 reads/writes, Qwen/Whisper/SentenceTransformer inference, real YouTube/Anthropic research, and browser layout/interaction across the full flow. Research dependencies `anthropic` and `googleapiclient` were absent in the implementation environment. A browser automation package was also unavailable. Model downloads/provider calls were not run. These features are connected in code and still require manual testing with your services; no end-to-end success is claimed.

Manual test sequence:

1. Sign in through Clerk; check the account name and Profile. Create two projects and confirm two separate tiles.
2. Open the first project, upload a short spoken MP4, submit a matching prompt, and check actual processing status. Confirm no success appears before completion.
3. Select an available clip and open the editor. Confirm its video/captions match the selection. Switch clips if multiple real matches were found.
4. Save the clip, open Exports, and download the MP4 and VTT. Play the MP4 locally and inspect the caption file. Export conversion controls should remain disabled.
5. Return to projects, reopen the project, and verify the name, source preview, prompt, previous generations, and saved clips. Submit another prompt against the restored source.
6. Choose speech search and visual search separately on the canvas and verify their real outputs. In the editor, render four caption presets; check four actual captioned results on the canvas and select any one.
7. Open an original upload in the editor and analyze a research topic with configured YouTube/Anthropic credentials. Reopen the project/editor and confirm the saved research result is restored.
8. Open the second project and confirm it has no clips/source from the first. Sign out, sign into another account, and confirm projects and clip access are isolated.
9. Check validation errors (empty prompt, invalid file), an unavailable service, and a restart during processing. Interrupted jobs should report failure; previously completed data should remain available.

## Changed files

- `app1.py`: project/user association, protected integration paths, backend dispatch, up to four real prompt matches, persisted failure metadata.
- `integration.py`: durable project records, ownership checks, saved clip references, source retrieval, and adapters for remote search/caption/research processing.
- `flow_C.js`: actual project API, profile, project-scoped navigation/history/source restore, clip selection, caption/research actions, save, and real downloads.
- `projects_C.html`, `canvas_C.html`, `editor_C.html`, `exports_C.html`: controls and containers for those features within the existing page layouts.
- `styles_C.css`: small additions for project tiles and real video/history containers; existing styling is retained.
- `backend/`: processing feature code and supporting resources from `origin/main`. Caption/search processing and app entrypoint are adapted as described above; the older frontend is not substituted for your site.
- `requirements.txt`, `backend/requirements.txt`: unified installation dependencies, MoviePy 2 API constraint, existing PyAV compatibility pin retained.
- `.gitignore`: virtual environment, caches, backend-generated media/settings excluded.
- `tests/test_integration.py`, `tests/render_smoke.py`: contract/ownership checks and reproducible real media rendering smoke test.
- `README_C.md`, `INTEGRATION.md`: corrected startup instructions, implementation boundaries, verification, and manual testing.

Neither `main` nor `cascade/new-website` was changed. Fetch updated remote references only. No pull, push, or merge into either original branch was performed.

Imported backend files (all new on the integration branch):

- `backend/app.py`
- `backend/clips/__init__.py`
- `backend/clips/render_subtitles.py`
- `backend/clips/router.py`
- `backend/requirements.txt`
- `backend/settings/__init__.py`
- `backend/settings/preferences.py`
- `backend/settings/router.py`
- `backend/settings/templates/settings.html`
- `backend/static/index.html`
- `backend/trends/README.md`
- `backend/trends/__init__.py`
- `backend/trends/pipeline.py`
- `backend/trends/router.py`
- `backend/trends/static/index.html`
- `backend/trends/youtube_trends.py`
- `backend/video_search/__init__.py`
- `backend/video_search/router.py`
- `backend/video_search/static/index.html`
