# Actual signed-in research request and saved punch-in

Verified on local `mlk` without provider, storage, or identity mocks. No credentials
or `.env` files were changed. Existing application authentication stayed enabled;
an unauthenticated request to `/api/projects` still returned 401.

## Browser-originated Analyze clip

The user clicked Analyze clip while signed in. Backend trace recorded:

- Research ID `7b4826e1519647b99cbd5d71154efb89`.
- Generation job `cd732c335cf041cda6e27f5169a1bf32`, clip index 1.
- Saved-edit render, FFmpeg frames, AI clip analysis, real public YouTube discovery,
  downloads, audio extraction, transcription, tutorial analysis and final synthesis
  completed successfully.
- Previously analyzed real-content example tags were reused from the provider
  cache; the tutorial and final clip-specific suggestions used actual AI calls.

Three analyzed sources were returned and persisted for the modal:

- https://www.youtube.com/watch?v=Jhs4vL3f5GM
- https://www.youtube.com/watch?v=RFsHtewjKn8
- https://www.youtube.com/watch?v=jNhjPCNG3Is

The missing Data API key remains handled by real public YouTube discovery, not
mock results. One unavailable candidate was skipped while successful sources were
retained. Nonfatal JavaScript challenge warnings did not block these downloads.

## Apply, save and render

At the user's request, the individual visual punch-in suggestion was executed via
the production editor chat → research Apply → action executor path. The service
integration reused the actual authenticated research job's owner context and normal
ownership checks. It did not forge a token, disable HTTP authentication, patch
identity verification, or claim a second authenticated HTTP/browser round trip.

The prior draft was backed up before saving. A fresh draft read confirmed the new
motion persisted. Only the motion edit field changed: one punch-in was appended.
Other manual settings, previous motion and previous chat were preserved.

The production export handler was invoked separately for the Edited preview payload
and the saved-draft download payload. Decoded video-frame hashes and decoded audio
hashes matched between the two renders. The before/after video hashes differ; matched
frames at 0.45 seconds visibly show the zoom. Original audio hashes are unchanged.
Duration remains 29.029 seconds.

Artifacts are in `/tmp/cascade-browser-real-apply/`:

- `draft-before.json`, `draft-after.json`, `research.json`, `application.json`
- `before.mp4`, `edited-preview.mp4`, `export.mp4`
- Matched-frame PNGs and `verification.json`

## Observability changes

Research now writes small rotating, sanitized per-process traces named
`cascade-trends-<pid>.log` in Python's temporary directory. Entries carry the research
ID, and include accepted Analyze requests, cache reuse, stage duration, failures and
completion counts. They omit headers, transcripts, provider payloads and secrets.
Terminal ANSI codes are stripped and YouTube's “This video is not available” message
is classified as `video_unavailable`. Thirteen targeted regression tests passed.

## Explicit verification boundary

Computer Use access was unavailable. The authenticated Analyze request and result
payload were observed through backend logs/persistence; the modal/source cards were
not visually inspected. Apply, saving and preview/export parity were verified by
production backend integration and actual rendered video, not browser automation.
No external service blocked completion of this run. The saved edit is available
when the frontend next loads that clip's draft.
