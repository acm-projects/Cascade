# Projects, generation groups and follow-ups

Projects use the existing owner-scoped JSON store under `video_jobs/projects/`. The hierarchy is source video → Session → Waves → Clips. Sessions are named, stored project objects; every new generation records its session ID before work is queued. Projects without stored sessions acquire a persistent Session 1 on read, and legacy generations without a session ID appear there without rewriting their job folders. Missing session IDs on new requests default to the first current session. Old owners default to four requested clips and no parent context; clip identifiers are derived from job ID plus zero-based result index.

## Interface

Each project card has a Delete action and native confirmation naming the project. Cancel sends no request. Failed deletion keeps the card and reports an error; active jobs must finish or be stopped before deletion. Successful deletion removes the card, its library entries and local selection/recovery references. Stale project URLs return to Projects; a storage event informs other open tabs.

The canvas retains the prompt and **Number of clips** control after each generation. Counts are whole numbers from 1 to 12, default 4. The technical ceiling bounds candidate selection and encoding work, and matches the existing hosted proposal capacity; it is not a commercial restriction. All engines receive the requested count. Selection returns distinct qualifying windows and may return fewer. Caption-style rendering remains a separate four-style operation.

Saved groups appear with creation order, prompt, status, requested/actual counts, errors or selection notes, and a parent reference where present. Earlier groups stay visible while a new request runs. Each clip has its own editor link and **Build on this clip** action. Follow-up selection shows the real parent media, title, prompt and original timestamps; Cancel restores ordinary full-source search. Preview media errors do not hide other clips or prevent editor links from rendering.

## Backend flow

- `/upload` accepts a new source and a validated `clip_count`, and records request metadata before queuing work.
- `GET /api/projects/{id}/generations` reconstructs all generation groups from owned jobs/results/failures, including legacy records. In-flight status uses the existing job registry; interrupted jobs become explicit failures after restart.
- `POST /api/projects/{id}/generations` accepts `prompt`, `clip_count`, `source_job`, `engine`, a submission `request_id`, and optional `parent_job`/`parent_clip_index`. Reusing the same request ID within a session does not enqueue a second generation. A fresh submission creates a fresh job rather than overwriting earlier results.
- A parent is identified internally as `<job UUID>:<zero-based clip index>`. The server resolves it through ownership-checked saved results, not browser-provided titles or timestamps. Parent context includes its original timestamps, previous prompt, description and available captions.
- Follow-ups resolve the canonical original source, including when the parent is itself a child. New jobs receive the complete source, preserving existing worker/export contracts and source-relative timestamps. Ordinary requests use the project's original upload. Identical-source analysis reuse remains owner/project scoped.
- Explicit expansion requests include the full parent plus available surrounding source footage, then retain only additional non-overlapping matches. If the parent already spans the source, no surrounding expansion is fabricated. Other instructions use semantic selection over the original with parent context. Natural-language selection quality still depends on the configured provider/model.
- The hosted selector uses bounded weighted interval scheduling rather than enumerating combinations, so larger requested counts do not create a combinatorial search. Local search and Ollama respect the same requested ceiling. Media routes and saved-clip selection support indices beyond four.

## Deletion and retained storage

`DELETE /api/projects/{id}` verifies ownership and stages only the selected project's records, editor drafts and exclusive job folders. A file-staging failure rolls back. Jobs referenced in another project's records/results retain their source/media and receive an inaccessible deleted-project marker; other projects are untouched. Live workers prevent deletion rather than racing with writes. Once staging succeeds, private staged local files are purged. If filesystem cleanup fails after logical deletion, private staging remnants can remain; they are not served.

Remote S3 objects are not purged by project deletion. Their project/job access is revoked through existing ownership checks. This avoids destructive cloud cleanup or removal of shared remote media. Live S3 behavior was not verified.

## Checks

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -q
node tests/test_editor_state.cjs
node tests/test_editor_flow.cjs
# With isolated headless Chrome on DevTools port 9333:
python3 tests/project_browser_server.py
# Separate terminal:
python3 tests/test_project_browser.py
```

The project browser fixture uses temporary storage, mocked identity/selection and real FFmpeg cuts. It checks five-clip and second ordinary requests, fewer results, parent cancel, expansion, child follow-up, reload, opening earlier/later clips in the real editor, failed group isolation, native delete cancel/confirm, persistent deletion and stale-link redirect. It does not establish live provider selection quality. Unit checks cover ownership, invalid counts, idempotency, source references, rollback and editor draft access across groups. Local pipeline tests mock model scoring but encode/probe four and five distinct real clips with audio and timed captions.

Existing Chrome editor tests also check actual playback/captions, history, per-clip restore, framing and real downloads after these changes. Live Clerk, paid OpenAI/Anthropic, YouTube, Ollama model quality and S3 are not exercised by these offline checks. Configuration and existing user data are not modified by the fixture servers.

## Horizontal branches and prompt history

The canvas now has a bounded horizontal branch viewport beside the composer on laptop screens. Every generation owns a unique column in a single horizontal strip. New full-video requests and siblings append to the right, and each follow-up is positioned to the right of its parent. No generation wraps onto a lower row. Clip cards stack vertically inside independently scrolling columns. The branch viewport supports horizontal wheels/trackpads, touch swipes, keyboard arrows, visible scrollbars and left/right buttons. On narrower screens the composer moves above the branches without widening the page.

`web/canvas_branches.js` derives placement from persisted job and parent IDs. It does not infer relationships from titles or clip numbers. SVG connectors link each parent clip to its child column, using an overhead connection rail when intermediate columns are present; when the parent card is outside its column's visible area, the endpoint clamps to that column's edge. **Reveal parent clip** brings the actual parent back into view. New pending requests scroll within the branch viewport and update the same column when done. Reload reconstructs the graph without enqueueing generation.

The **Prompt history** drawer lists submitted requests chronologically with prompt, timestamp, count, state and source context. Clicking an entry reveals/highlights its generation column. **Reuse prompt** copies text/count and restores the source context without submitting; submitting after review creates a new request. Missing parents require choosing a valid clip or explicitly switching to a full-video search.

History is the existing owner/results/failure/progress record set, with additive `history_id` and `creation_order` metadata for new submissions. Both are stable across retries. No migration is needed: legacy records derive IDs from their jobs and order/time from existing records. A legacy retry freezes the derived values before modifying its owner record. Uploads save owner and queued progress before dispatch, and missing OpenAI configuration or queue failures remain visible as failed requests rather than disappearing.

`POST /api/projects/{id}/generations/{job}/retry` accepts a unique `request_id`. It validates ownership, original-source and parent availability, restores the saved prompt/count/method/context, and requeues the same generation. It clears stale failure/cancellation state and records attempt IDs, timestamps and the previous failure under `retry_attempts`. Repeated tokens and requests for an active retry do not enqueue duplicate work. Completed generations must use Reuse instead. Deleting the project removes this history together with its existing project/job records (subject to the shared-media and S3 retention described above).

Additional checks:

```sh
node tests/test_canvas_branches.cjs
# With project_browser_server.py and isolated Chrome running:
python3 tests/test_horizontal_browser.py
```

The horizontal browser check verifies unique rightward columns for roots, children and siblings, no wrapping, connectors, pending-column identity, scrolling without moving the page, horizontal wheel and synthesized touch gestures, history jump/highlight, reuse, missing-parent metadata and blocked-media handling, retry without duplicate groups/history, reload, 480px page width, per-column scrolling, editor playback, and deletion while preserving another project's saved history. It uses mocked selection/identity with real local HTTP persistence and real video cutting. Synthesized Chrome touch is not physical-device or Safari/Firefox verification. A real fixture screenshot is written to `/tmp/cascade-horizontal-branches.png`.


## Stored sessions, selections and multiple references (CAS-20/21/22)

The session API supports GET/POST `/api/projects/{pid}/sessions` and PATCH/DELETE
`/api/projects/{pid}/sessions/{sid}`. Names are trimmed and limited to 1–60 characters.
Deleting the last session or a session with an active worker returns 409. Session
removal marks its jobs inaccessible without deleting media. GET generations accepts
`?session_id=...`; labels follow the stored session order in both generation history
and the editor.

GET/POST `/api/projects/{pid}/sessions/{sid}/selections` lists/adds examples;
DELETE `.../selections/{number}` removes one. GET `/api/projects/{pid}/selections`
joins all sessions' selections with clip data and session names. Project detail
includes `selection_count`. A session's selection counter only increases: removing
Selected 2 never assigns that number to a different clip. Re-selecting an existing
clip returns its current entry with 200 rather than assigning another number.
Selection updates run under the existing project lock, including concurrent requests.

Generation requests accept `session_id` and up to six positive integer
`reference_numbers`, for example `[2, 4]`. When that list is absent or empty, the
backend parses explicit markers in the prompt: `clip 2 and 4`, `selected 1, 2 & 5`,
or `#3`. Ordinary counts such as `give me 2 funny clips` are not references.
Unknown selections return 400; references must belong to the owned project,
chosen session, and same original upload. Without an explicit `source_job`, references
identify the source; an ordinary request uses the session's earliest available upload.

Each job records `reference_clips` before queuing. This immutable snapshot contains
selection numbers, job IDs, clip indices, original timestamps, titles, previous
prompts, descriptions and up to 4,000 caption characters. The first reference is
also stored as `parent_clip` for older clients. Legacy parent requests still work.
Generation history returns all reference edges; retries preserve the original snapshot.
Multi-example prompts ask the agent to find new moments sharing the examples'
characteristics. Agent and local search discard candidates overlapping more than
half of the shorter interval (candidate or example). An explicit single-example
expansion remains supported and deliberately includes the parent with surrounding
footage; multiple examples never trigger automatic expansion.

The current repository keeps generation routes in `backend/project_actions.py`,
project persistence in `backend/integration.py`, and upload processing in `app1.py`.
These existing locations are extended rather than requiring the planned router refactor.
No frontend selection UI or multi-edge rendering is introduced by this backend change.

Focused verification:

```sh
python -m unittest tests.test_references tests.test_generation_groups tests.test_editor_navigation tests.test_main_editor_integration tests.test_logout -q
```


## Project source upload (CAS-19)

`POST /api/projects/{project_id}/source` accepts multipart `video` independently of
any prompt. It returns 202 with `source_job` and `status: processing`. The project
stores `source_job`, `source_status`, `source_duration`, `thumbnail_url`, and
`source_error`. A second source upload returns 409, including after preparation
failed; use a new project for a different source. Source records use `kind: source`
and belong to the project rather than a session.

The preparation worker probes the media, atomically writes a 640-pixel-wide JPEG
at 10% of the duration, then calls the same `build_index` and `ensure_summaries`
functions as the clip agent. Existing content-hash/provider/model cache keys let
later generations reuse the frame embeddings, transcript, transcript embeddings,
and summaries. The thumbnail is available from the owner-protected
`GET /api/projects/{project_id}/thumbnail` while the expensive index is still
processing. Preparation finishes as `ready` or records a safe `error` message.
Project deletion is blocked while source preparation is active.

A generation can supply only `prompt`, `clip_count`, and `request_id`; the session
defaults to the first session and the source defaults to the project's source.
An unprepared project source returns 409. Legacy projects with original uploads
can continue resolving those uploads, and the combined `POST /upload` flow remains
available. Both upload paths share streaming save, SHA-256 fingerprinting, empty-file
validation, owner persistence, and cleanup. The old upload path has no extension
or upload-size policy; this change preserves that policy and validates video media
through FFprobe during preparation.

Offline source checks mock transcription and AI services. A generated five-minute
video additionally exercises real FFprobe inspection and FFmpeg JPEG rendering:

```sh
python -m unittest tests.test_project_source tests.test_references tests.test_generation_groups tests.test_editor_navigation tests.test_main_editor_integration tests.test_logout -q
```
