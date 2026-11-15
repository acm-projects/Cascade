# Generation latency and long-source validation

Ordinary spoken-content, highlight, mood, and follow-up searches use transcript-first
batch selection. Explicit visual/action requests retain multimodal indexing and inspection.
Up to 12 requested clips use one structured selection call, with at most one repair/refill.
This path does not load embedding models or make a separate AI intent-classification call.
Larger batches retain the summarized tool-agent flow; visual requests keep their existing
evidence checks. Batch descriptions must be supported by the transcript, not invented visuals.

Selection input is capped at 72,000 transcript characters. Smaller transcripts remain
complete. Larger transcripts use intact windows ranked against prompt/reference wording
and balanced across the timeline, including opening and closing windows. Candidates may
not cross omitted transcript material. This is a latency/recall tradeoff: a relevant moment
can be missed by retrieval, so a live relevance benchmark is still required.

Single-reference, single-output requests such as `keep the first 8 seconds` or
`keep the last 8 seconds` use cached source captions and direct timestamp edits, with
no transcription or AI calls. Ambiguous commands, missing caches, similarity searches,
multiple references, and multiple outputs use the normal selection path. Source-relative
timestamps, ownership checks, and caption offsets are preserved.

Cloud source backup runs on a separate bounded executor after normalization, instead of
blocking analysis. Its pending/complete/failed state is persisted in the owner's metadata;
the local source must be retained until backup succeeds. A backup failure does not fail
clip generation or claim that a durable cloud copy exists. Restarted pending backups are
not automatically resumed; retry the original generation to reschedule one.

Multimodal indexing builds the transcript and visual indexes concurrently. Progress callbacks
run on the calling thread to preserve cancellation and job-state serialization. Existing
transcript, embedding and summary caches are retained.

Verified follow-up uploads reuse source bytes with a hard link when possible, falling back to
a copy across volumes or when hard links are unavailable. The original ownership checks run
before reuse. Clips become available as a stable, ordered prefix while later clips render.
Publication uses existing authenticated local media routes and does not wait for cloud saving.
The final local results record is written after all encodes complete. This preserves clip indexes.
`first_clip_ready_seconds`, `index_mode`, `index_timings` and `selection_mode` are recorded
with completed job results. Timings exclude browser upload time.

## Local playback and cloud backup

CPU FFmpeg still uses the same x264 `veryfast` settings, source resolution,
precise input seeking, AAC audio, and caption timing. Up to half the logical CPU
count can encode separate clips concurrently; encoder threads share that CPU budget.
Normal progress updates are immediate in memory and coalesced onto one background
metadata writer. Versioning and per-job writer locks prevent an old progress update
from overwriting final success/error; final saves remain synchronous.

Once local results are persisted, clip cloud uploads run through three shared upload
workers, separately from generation. Each MP4/MP3 and its VTT are uploaded together
as one clip task; different clips upload concurrently. Results and the UI distinguish
`pending`, `complete`, and `failed` backup states. Local files are retained on every
outcome. Clip backup failure does not turn playable clips into a generation failure.

`POST /api/projects/{project_id}/generations/{job_id}/backup/retry` checks project/job
ownership and retries only clips missing durable media/caption keys, without AI or
rerendering. Interrupted pending manifests resume at application startup. Batch tokens
and deletion checks prevent stale backup tasks from recreating removed/newer jobs.
The Studio chat exposes backup failure/retry and keeps polling while backup is pending.

`encode_seconds` records each clip's FFmpeg duration, `upload_seconds` records its
cloud upload task, and `cloud_backup_seconds` records the background batch. The legacy
`Video rendering and storage` timer now covers local rendering/publication, not cloud
upload completion. Do not compare that aggregate with older runs without accounting
for the changed boundary. Different generation jobs still share a single generation
worker; this change parallelizes clips/uploads without oversubscribing whole jobs.

## Offline mechanics check

Run from the repository root:

```sh
python tests/manual/benchmark_long_video.py --fixture --output .test-tmp/long-video
```

This creates a low-resolution 2h10m, four-color video with an audio track and runs real
FFmpeg clip/caption rendering, local storage and result persistence. It verifies duration,
caption format and the actual frame color of clips from all four source chapters, including
a clip starting at 2:06:40. **AI selection is mocked. This is not evidence of documentary
semantic quality, real provider latency, or production-resolution encoding performance.**

## Live documentary check

After selecting an authorized source and approving provider use:

```sh
python tests/manual/benchmark_long_video.py --source documentary.mp4 --live --output .test-tmp/documentary
```

This uses configured Deepgram and AI services and can incur charges. The source must be at
least two hours long. Keep the resulting benchmark JSON and generated clips private. Review
the actual clips for relevance and natural boundaries; automated timestamp checks cannot
establish semantic quality. Initial upload, transcription and encoding still take time;
no instantaneous processing guarantee is implied.

## Research integration

`backend/agent/` selects clips. `backend/trends/` and `backend/services/features.py`
compare an upload against trending YouTube videos as a separate research operation. They
share transcription/provider infrastructure; trend research is not run for ordinary clipping.
`backend/agent/research.py` stores clip-run findings and is not the trends research engine.

## Limits of the local speed changes

No provider-backed benchmark was run for these changes. First-upload transfer,
normalization, transcription, model response time, and full-resolution encoding still
contribute to latency. Pre-upload analysis and streaming timestamp previews are not enabled;
analysis still starts on Generate, and previews still use rendered clips. The changes do
not establish a universal sub-30-second guarantee and do not trigger paid preprocessing
when a user merely selects a file.
