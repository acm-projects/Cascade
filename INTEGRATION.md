# Cascade integration

Branch: `cascade/integration`, based on `cascade/new-website` at `1740bd8b276c799a99a38a62e30a30e72c5729f2`.
Backend source: current local `main` (also previously fetched `origin/main`) at `49c529b249fbd044f85e5bfb6eb84b47b0d6621c`.
All three local branches were inspected for this follow-up. Local `main` now matches the previously integrated backend source, so no additional Git merge was needed. Settings and research accessibility were completed through code changes exclusively on `cascade/integration`. The stash named “Preserve local files before updating main” was not applied, changed, or dropped.

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
- Account settings use the teammate preference fields (video type, audience, tone, goal, platforms) and their persistence helper. Open **Settings** in the account bar. Saves and reloads are isolated per user; existing root/backend preference files remain unchanged. The teammate processing algorithms do not consume these fields to change output, which is stated on the page.
- Trend research from `main` compares the original upload with current YouTube videos using Whisper and Anthropic. Research is available on both the canvas and editor, including before clip generation. Actual pipeline progress is shown; readable comparison results and YouTube links replace the raw JSON display. Caption style jobs retain an owned parent-job reference so research can find the original upload. Results are saved and restored.
- Save Clip persists an actual job/clip reference, rather than claiming an edited video has been rendered. Exports displays selected/saved real clips, downloads the existing MP4, and downloads actual VTT captions. Speech/visual search and caption styles also burn captions into the MP4.
- Previous user-owned clips without a project association remain downloadable from **Previous generated clips** on the projects page. Their ownership files and media are not migrated or overwritten.

## Storage and configuration

No SQL/Neon database code exists in either inspected branch. No database configuration was replaced and no SQL migration is required. This is an additive local-filesystem implementation using the website backend's existing `video_jobs` directory, not a claim of Neon integration.

New projects live at `video_jobs/projects/<SHA256-of-user-ID>/<project-ID>.json`. Job ownership records for new uploads additionally include `project_id`, `prompt`, and `source_name`. Saved clip references live in the project record. Account preferences live at `video_jobs/projects/<SHA256-of-user-ID>/settings/preferences.json`; existing preferences are read as initial defaults, then account changes are stored separately. New derived jobs include an optional `parent_job` link. Existing job directories are left intact. Back up `video_jobs` and retain it across service restarts/deployments; S3 holds generated media, but does not hold the project index or original uploads. There is no multi-process database locking: run one Uvicorn worker on one persistent filesystem.

Existing `.env`, Clerk validation/configuration, AWS credential resolution, S3 bucket/region, and root preferences files remain unchanged. No secrets are included in the integration files. Do not commit `.env`, runtime records, or generated media.

`backend/` contains feature source copied from fetched `origin/main`. `backend/app.py` delegates to the authenticated website app. The old standalone search/clip/trend routers and diagnostic HTML are not mounted publicly; `integration.py` calls their processing functionality behind Clerk and ownership checks. `/settings` opens the updated settings page. Its authenticated JSON API reuses the teammate persistence helper with a per-user destination. The original standalone global form/router source is retained and not mounted publicly.

## Unfinished behavior

Free-form editing chat, editable caption text/fonts/colors/placement, timeline edits, aspect ratio/cropping, subject tracking, B-roll uploads/generation/compositing, merged multi-clip sequences, format/resolution conversion, and direct social publishing have no integrated implementation. Those existing controls stay disabled or explicitly labeled unfinished. Selecting clips opens one selected clip at a time, rather than assembling a multi-clip sequence. The four caption treatments are rendered presets; tone/audience inputs in the old renderer do not affect rendering.

There is no cross-device source upload storage, automatic interrupted-job retry, or project database synchronization. The browser reloads the saved source as a Blob/File, so opening a large project downloads its source into browser memory. Clip playback/download also retains the existing authenticated Blob approach.

## Install and run

### Windows local processing and troubleshooting

**AI scene analysis now uses OpenAI by default.** Ollama is not required for it.
Keep your existing `.env` and add the following locally (do not commit the key):

```dotenv
OPENAI_API_KEY=your_key_here
# Optional; these are the defaults:
OPENAI_SCENE_MODEL=gpt-5.4-mini
OPENAI_SCENE_REASONING=low
OPENAI_SCENE_TIMEOUT=120
OPENAI_SCENE_MAX_FRAMES=48
```

Choose **AI scene analysis — OpenAI · up to 4 clips** and enter a request such as
“Find four funny moments; include each setup and punchline.” The app transcribes
speech locally (or reuses the saved transcript), extracts up to 48 compressed
timestamped images, and sends the images plus transcript to OpenAI's Responses
API with a strict candidate schema and `store=false`. It does not upload the
full source video to OpenAI. Normal processing uses one scene-selection call;
a transient rate/service error may retry once. API usage is billed to your key.

The selector requests up to 12 candidate windows and validates finite timestamps,
source bounds, duration, match score, duplicates, and overlap. It chooses up to
four distinct supported moments without merging adjacent candidates. It does not
repeat one joke or pad unrelated footage to force four clips. Fewer results come
with a readable explanation. Humor quality still needs testing on your footage.
Boundary validation ensures usable windows, not that a moment is objectively funny.

FFmpeg cuts the clips locally and matching VTT captions are generated from the
transcript. Existing Clerk ownership and local/S3 media delivery remain in use.
Model results, usage, and timings persist with the job; identical requests reuse
the paid selection within the same account/project. Changing the prompt, model,
frames, transcript, or requested duration invalidates that selection cache. Cache
metadata lives in `openai_selection.json`; keys are never saved there or sent to
the browser. No OpenAI SDK installation is needed; the existing HTTPX dependency
implements the documented API protocol.

The timing panel includes local transcription, preview extraction, OpenAI scene
selection (including network wait), validation, rendering, and storage. Missing
keys, rejected keys, quota/rate limits, refusals, incomplete responses, and timeouts
produce readable errors. The Stop button takes effect at the next checkpoint;
an in-flight request may still complete and incur usage.

All automated tests mock OpenAI. The migration has **not** been tested with a live
OpenAI request: the user asked to perform the first live upload themselves. The
earlier timings below are local-model measurements, not OpenAI speed claims.

From PowerShell in the repository root, use the Python 3.12 environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

The API serves the website too. Restart it after changing environment variables or source files.

Storage defaults to `CASCADE_STORAGE=auto`: generated media stays on this computer if
`S3_BUCKET_NAME` is absent, and uploads to S3 when a bucket is configured. Set
`CASCADE_STORAGE=local` explicitly to avoid S3 uploads on a slow connection. Local
clips retain the same Clerk authentication and ownership checks. Keep `video_jobs`
on disk; local storage is not a cross-device backup. `CASCADE_STORAGE=s3` requires
`S3_BUCKET_NAME`, AWS credentials (`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`,
or an AWS credential profile), and the correct `AWS_DEFAULT_REGION`. A configured
but failing S3 upload reports an error; it does not silently change storage modes.

Clerk expects `CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY`. For compatibility,
`CLERK_KEY` is accepted according to its `pk_`/`sk_` prefix, and `AWS_ACCESS_KEY`
is accepted as an alias for `AWS_ACCESS_KEY_ID`. An AWS access key ID alone is
insufficient: it still needs its paired secret access key. Existing `.env` values
are never rewritten by the app.

The canvas shows both overall processing time and time in the current step.
The **Processing timings** panel also shows completed stage durations, including
model loading, frame extraction, prompt/image embeddings, Whisper transcription,
rendering, and clip storage. These measurements use a monotonic clock and include
Whisper's lazy segment iteration. A currently running stage has a live elapsed
counter. Completed breakdowns are saved in `results.json` and restored with job
history; timing fields are also included in status responses. They exclude the
browser's initial upload and subsequent playback downloads. AI scene analysis
reports its own broader stages rather than image embeddings, which it does not use.
`video_jobs/<job-id>/progress.json` saves the last progress update. A status response
with HTTP 200 only confirms that polling succeeded; inspect `state` and `message`
for processing status. API terminal logs include each stage and Ollama's reported
model/load durations. **Stop processing** requests cancellation at the next progress
checkpoint; an active model request or FFmpeg process must return or time out first.

The optional **Local Ollama analysis** still performs vision inference and transcription; it is not
instant. Defaults now use 4,096 context tokens and at most 20 AI-analysis frames,
each fitting within 384×384 pixels,
and scoring batches of up to eight observations. Long videos are sampled more
sparsely, so very brief events may be missed. Repeated AI requests on an identical
upload reuse transcripts and visual descriptions within the same account/project.
Speech search avoids the vision language model. Visual search samples across the
whole video and transcribes only the selected clip for captions; silent videos
do not load Whisper just for captions. First use may download model files.

AI analysis combines each group into one numbered contact sheet (up to 672×488),
read chronologically. This reduces per-image token overhead. Scene descriptions
are capped at 128 output tokens. If a request still exceeds context, the group is
split into smaller chronological requests, preserving sampled frames and their
time window. The app does not automatically increase context memory. Local CPU
vision inference can still be slow, particularly under RAM pressure. Increase
`CASCADE_AI_MAX_FRAMES` (default 20, maximum 100) for denser sampling at the cost
of additional model calls. Cached visual descriptions are versioned by sampling
settings so partial results from older layouts are not combined with new layouts.

Limits can be overridden in `.env`: `CASCADE_MODEL_TIMEOUT=120` (seconds per
Ollama request), `CASCADE_FFMPEG_TIMEOUT=300` (seconds per FFmpeg command),
`CASCADE_JOB_TIMEOUT=900` (AI job budget checked between processing steps),
`CASCADE_MODEL_CONTEXT=4096`, and `CASCADE_MODEL=qwen3-vl:4b-instruct`.
These are failure limits, not speed guarantees. The job budget and cancellation
are cooperative, rather than forcibly killing an in-flight native model operation.

Validation:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# Opt-in: starts real local Ollama inference on a four-second synthetic silent video.
# No S3 or paid API calls; all synthetic media is temporary.
.\.venv\Scripts\python.exe tests/live_ai_smoke.py
# Opt-in: real visual search and captions on your own file, cached models only.
.\.venv\Scripts\python.exe tests/live_search_smoke.py path\to\video.mp4
```

An earlier local-model smoke test completed in 102.5 seconds on this machine: 79.3 seconds in
vision inference (including 10 seconds loading), 8 seconds interpreting the query,
and 14.5 seconds scoring. It produced a playable local clip. This validates one
small synthetic AI path, not arbitrary-video quality, live speech inference,
Clerk browser sign-in, or AWS access. Hardware/memory pressure and first-use model
downloads can materially change these timings.

A separate offline test on the existing 133.5-second uploaded video completed
real visual search, Whisper captions, and a 30-second MP4 render in 21.1 seconds,
including roughly 13 seconds importing dependencies. Models were already cached;
no S3 or provider calls were made. Local visual search remains available alongside
the new default OpenAI scene analysis. These are different
search algorithms and inputs, so these timings are not a before/after speedup claim.

Use Python 3.12 and FFmpeg/ffprobe. Ollama is only required for the optional local
Ollama analysis mode. From the repository root on macOS:

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

- Twelve HTTP/persistence/ownership/selection/settings/research/caption-adapter tests. Identity verification and worker/provider calls are mocked for these contract tests; this does not certify live Clerk, S3, or AI services.
- Python compilation and JavaScript syntax checks.
- Four actual MoviePy/FFmpeg MP4 renders with audio, matching VTT output, and FFprobe verification, using synthetic media and mocked Whisper transcription.
- Real Uvicorn startup and HTTP checks for pages/assets, `/api/health`, and unauthenticated API rejection. The temporary test server was stopped afterward.

Not exercised: live Clerk sign-in/profile/sign-out, AWS/S3 reads/writes, Qwen/Whisper/SentenceTransformer inference, real YouTube/Anthropic research, and browser layout/interaction across the full flow. Research dependencies `anthropic` and `googleapiclient` were absent in the implementation environment. A browser automation package was also unavailable. Model downloads/provider calls were not run. These features are connected in code and still require manual testing with your services; no end-to-end success is claimed.

Manual test sequence:

1. Sign in through Clerk; check the account name and Profile. Create two projects and confirm two separate tiles.
2. Open the first project, upload a short spoken MP4, submit a matching prompt, and check actual processing status. Confirm no success appears before completion.
3. Select an available clip and open the editor. Confirm its video/captions match the selection. Switch clips if multiple real matches were found.
4. Save the clip, open Exports, and download the MP4 and VTT. Play the MP4 locally and inspect the caption file. Export conversion controls should remain disabled.
5. Return to projects, reopen the project, and verify the name, source preview, prompt, previous generations, and saved clips. Submit another prompt against the restored source.
6. Choose speech search and visual search separately on the canvas and verify their real outputs. In the editor, render four caption presets; check four actual captioned results on the canvas and select any one.
7. On the canvas, choose a video and analyze a topic under **Research current trends** before generating clips. Check actual processing messages and the comparison/YouTube links. Also test research from the editor, including a newly rendered caption style. Reopen the project and confirm research results are restored. This requires YouTube/Anthropic credentials.
8. Open the second project and confirm it has no clips/source from the first. Sign out, sign into another account, and confirm projects and clip access are isolated.
9. Open **Settings**, save preferences, reload, and verify they are restored for this account. Switch accounts and confirm edits are isolated. Preferences are saved but do not yet change generated content.
10. Check validation errors (empty prompt, invalid file), an unavailable service, and a restart during processing. Interrupted jobs should report failure; previously completed data should remain available.

## Changed files

- `app1.py`: project/user association, protected integration paths, backend dispatch, up to four real prompt matches, persisted failure metadata.
- `integration.py`: durable project records, ownership checks, account settings, saved clip references, source retrieval, original-video lineage, research-only uploads, and adapters for teammate search/caption/research processing.
- `flow_C.js`: actual project API, profile, project-scoped navigation/history/source restore, clip selection, caption/research actions, save, and real downloads.
- `projects_C.html`, `canvas_C.html`, `editor_C.html`, `exports_C.html`, `settings_C.html`: controls and containers for those features within the existing page layouts.
- `styles_C.css`: small additions for project tiles and real video/history containers; existing styling is retained.
- `backend/settings/preferences.py`: compatible optional per-user storage destination and atomic writes, retaining legacy defaults.
- `backend/trends/router.py`: optional processing progress callback; existing standalone callers remain compatible.
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
