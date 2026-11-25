# Generation latency and long-source validation

Ordinary spoken-content, highlight, mood, and follow-up searches use transcript-first
batch selection. Explicit visual/action requests retain multimodal indexing and inspection.
Up to 12 requested clips use one structured selection call, with at most one repair/refill.
This path does not load embedding models or make a separate AI intent-classification call.
Larger batches retain the summarized tool-agent flow; visual requests keep their existing
evidence checks. Batch descriptions must be supported by the transcript, not invented visuals.

Selection input is capped at 200,000 transcript characters (about 3 hours of speech).
Smaller transcripts remain complete. Larger transcripts use intact windows ranked against
prompt/reference wording and balanced across the timeline, including opening and closing
windows. Candidates may not cross omitted transcript material, so a relevant moment in an
omitted window can be missed. See "Selection quality check" below for how the cap was chosen.

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
for the changed boundary. Up to `CASCADE_GENERATION_WORKERS` jobs (default 2, one per
person) run at once; their encodes split the CPU cores between the running jobs, so
parallel jobs do not oversubscribe the machine (see docs/setup.md).

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

## Selection quality check

`scripts/eval_selection.py` measures clip choice on saved transcripts (no video, no new
transcription; a few cents of AI calls). It joins several transcripts into one long talk,
hides ten moments spread through it (an AI writes a search for each from the passage
alone) and checks whether the app's transcript selection returns them. Five general
requests ("funny moments", "interesting highlights", ...) are scored 1–5 by a separate AI
call for fitting the request and making sense on their own. Each run compares input limits.

```sh
python scripts/eval_selection.py backend/agent/.cache/transcript_A.json backend/agent/.cache/transcript_B.json --style plain
python scripts/eval_selection.py ... --style indirect   # searches that avoid the passage's own words
```

Results on 24 Nov 2026 (three real podcast transcripts joined: 117 minutes, 131,661
characters; `gpt-6-luna`). The old 72,000-character cap showed 55% of this talk; it
turned out to be about 70 minutes of speech, not 1.5–2 hours.

| | 72,000 characters | Whole transcript |
|---|---|---|
| Hidden moments found, searches naming the subject (2 runs) | 20/20, all as first pick | 20/20, all as first pick |
| Hidden moments found, searches in other words | 8/10 | 8/10 |
| General requests: fits the request (avg of 3 runs, 1–5) | 3.6 | 4.0 |
| General requests: makes sense alone (avg of 3 runs, 1–5) | 3.2 | 3.4 |
| Time per request (median, 1 run) | 5.8 s | 5.3 s |
| Selection cost per request | ~$0.004 | ~$0.006 |

Specific searches were rarely hurt by the cap, because windows are ranked by the search's
own words; only one of 40 hidden moments was outside the text shown, and the whole
transcript missed that one too. General requests did better with the whole transcript in
every run, at the same speed, so the cap was raised to 200,000 characters. Scores vary by
about 0.5 between identical runs, so compare several runs before trusting a small change.
The judge reads words only: it cannot see visuals, delivery or edit quality.

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
