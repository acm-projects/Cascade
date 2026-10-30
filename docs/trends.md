# Clip Trends and executable research

See [real pipeline verification](live-research-verification.md) for the subsequent
live YouTube/Deepgram/OpenAI run, discovery fix, stage diagnostics and stronger
flashy profile. That live run supersedes this document's original mocked-only
verification limitation.

Implemented locally in the existing `mlk` React editor. No commit, merge, push,
stash application, secret-file edit, or publishing action is part of this work.

## Use it

Run the existing backend from the repository root:

```sh
CASCADE_WARM_MODELS=0 .venv/bin/python -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

Run the existing React development server in another terminal:

```sh
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173**. Authenticate, open a project and select a video in
Editor. Open **Trends → Analyze this clip**. The initial editable topic comes from
the title/dialogue; analysis refines searches using topics from the actual edited
frames. Research is also available under **Trends · YouTube research** on Exports.
Both locations read the same owner/clip-scoped results.

Trends now opens a shared large modal over Editor or Exports. It includes the
selected Original/Edited preview, topic, progress, findings, timed suggestions,
YouTube thumbnail cards, fox/read-aloud controls and explicit Apply actions.
Opening and analysis are read-only. Previous findings remain visible during a
retry, and changed/expired results cannot be applied. Escape closes, focus stays
inside the dialog and returns to the trigger, background scrolling is locked, and
the body scrolls with a single-column mobile layout. Test fixtures are explicitly
marked as test data. See `TrendsModal.jsx` and `TrendsPanel.jsx` in
`frontend/src/features/editor/`.

Research renders a snapshot of the submitted current edits, rather than following
the generation job to its full original upload. The UI flushes autosave first.
Analysis does not modify the edit draft. Results show strengths, suggestions,
source timestamps, source links, publication dates, view counts, research/expiry
time, repeated example traits and coverage failures. Tutorials contribute explained
techniques, not the presenter's visual style. Their title is also checked to avoid
mistaking a tutorial found in the examples search for an example edit.

The fox guide has a text explanation and explicit **Read aloud / Stop reading**
controls using browser speech synthesis. It never autoplays. Voice availability
and quality depend on the browser/OS.

**Apply suggested edits** executes the bounded High-Energy style. Research hook and
visual suggestion times inform opening/punch-in selection; speech safety, measured
beats and the effect budget decide final timings. Individual suggestion buttons
execute the selected supported technique through editor chat. Results report actual
applied/skipped/failed steps and return the complete resolved edit specification.
They are not arbitrary tutorial-to-code translation. Undo restores the previous
state; autosave persists edits and chat. Exports also offers undo/redo for this flow.

Chat requests such as **“Make this a crazy, flashy TikTok-style edit”** invoke or
reuse fresh YouTube research and execute this supported style. If research fails,
the local style can still execute and the research failure is reported explicitly.
This does not establish that anything is a verified TikTok/Instagram trend or will
go viral. Ordinary precise editing requests keep the existing executor behavior.

## Real editing primitives

- Complete-phrase opening and confirmed silent-pause removal, preserving speech.
- Measured music beats align punch-ins, cutaways and a safe pause cut when a beat
  fits within the confirmed silence. Existing source shot cuts are not all moved.
- Pause-only pitch-preserving ramps in eight steps; no accelerated dialogue.
- Up to three restrained punch-ins, one subtle shake, a brief blur accent, short
  cutaway dissolves and entrance/exit fades; no random flash stacking.
- Short animated caption groups and highlighted keywords, with estimated timing
  within transcript cues rather than forced word alignment.
- Relevant private B-roll assets, music, one quiet whoosh, fades and transcript
  ducking. Missing stock is a visible partial failure; successful edits survive.
- A shared source/output clock retimes captions, audio and effects. Edited preview
  and MP4 download use the same actual server renderer, not CSS approximations.

Fit composition is required for retimed footage. The coordinated style chooses
Fit and preserves the chosen ratio. Set portrait ratio manually if desired. The
style replaces its effect arrangement; review and undo as needed.

## Setup and scope

Existing configuration names only; no values or files were changed:

- `YOUTUBE_API_KEY`: YouTube Data API discovery.
- `DEEPGRAM_API_KEY`: reference/tutorial transcription.
- `LLM_PROVIDER`: `anthropic` or `openai`, and that provider's
  `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.
- `PEXELS_API_KEY`: existing automatic stock search, if B-roll is requested.
- Existing FFmpeg/ffprobe setup (libass for captions), Python dependencies and
  authenticated application/storage configuration.

No new rendering library or paid editing service was introduced. Local procedural
music remains available without a music provider; user uploads are supported.
Live research may make multiple paid transcription/AI requests and YouTube quota
requests. Each run attempts up to two examples and one tutorial from the last 14
days. Downloads are limited to 10-minute references with bounded retry/socket waits.
Five sampled frames cannot establish precise motion or prove a sound is trending.

`backend/editor/trends.py` owns clip-specific background jobs, state fingerprints,
six-hour TTL, provenance, suggestion validation and application. Routes:

```text
POST /api/projects/{pid}/editor/{jid}/{index}/trends
GET  /api/projects/{pid}/editor/{jid}/{index}/trends[?research_id=...]
POST /api/projects/{pid}/editor/{jid}/{index}/trends/apply
```

Results are private metadata beside editor drafts, separated by owner, project,
job and clip. Cached analyses include normalized topic, model, edit fingerprint and
pipeline revision. Stale or different-edit application returns 409. Interrupted jobs
are reported after restart. Legacy source-research routes remain available; their
aggregation, result TTL and provenance have also been corrected.

## Verification and sample

```sh
CASCADE_WARM_MODELS=0 .venv/bin/python -m unittest tests.test_clip_trends tests.test_high_energy_reel tests.test_advanced_editing tests.test_editor tests.test_broll -q
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run lint
CASCADE_WARM_MODELS=0 .venv/bin/python scripts/demo_trends.py /tmp/my-new-trends-demo
```

The demo copies the available Teddy clip into temporary storage. It runs the real
research job/render boundary, chat application, save/reload and MP4 export, with
**mocked YouTube, AI, transcription analysis and stock search**. Source media,
cutaways, timing, captions and audio rendering are real. It writes playable
`original.mp4`, `edited.mp4` and a detailed `report.json`; no existing media is changed.
The final recorded sample is `/tmp/cascade-trends-demo-final/`: original 36.83s,
edited 32.20s. Its `verification.json` records matching audio/video duration,
added-audio residual energy, peak level below clipping, and 0.972–0.997 dialogue
correlation at four output windows. Matched source/output frames were inspected
for actual punch-in, caption, grade and local cutaway changes. This is signal/frame
verification; subjective listening remains a user check.

`tests/test_trends_browser.py` uses the isolated server in
`tests/advanced_editor_browser_server.py` with `CASCADE_FIXTURE_PORT=8782` and a
separate Chrome debug profile on port 9352. It verifies analyze/apply, citations,
guide/read/stop wiring, undo/redo, reload, shared Exports results and mobile overflow.
Browser speech playback is mocked, so actual OS voice output remains manual.

Live YouTube discovery/download/transcription/AI research has not been exercised in
this task. No credentials were inspected. Real-provider relevance, availability,
quota and subjective listening/voice quality remain manual checks. The existing
dotenv loader warns about line 9; that secret file was not inspected or rewritten.

Still unsupported: arbitrary tutorial reproduction, masking/rotoscoping, glow/3D
compositing, generative footage, optical-flow ramps, reverse/freeze-frames, exact
word alignment and broad web or verified cross-platform trend discovery. Post copy
is never overwritten and no external account actions are taken.
