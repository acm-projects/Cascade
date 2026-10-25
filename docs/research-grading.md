# Clip and wave research (CAS-50, CAS-51, CAS-52)

Research uses the existing YouTube transport and `cascade_llm` provider selection.
Set `YOUTUBE_API_KEY` plus the key for `LLM_PROVIDER` to use grading. Neither the
YouTube quota nor paid model calls are needed for the automated tests.

## Similar Shorts service

`backend.research.similar.find_similar_shorts(context, limit=8)` returns validated
`Short` objects. One structured model call builds a short query from the title,
first 60 transcript words and session prompt; title keywords are the fallback.
Query construction and query results are cached for 24 hours under the ignored
`backend/research/.cache/research/` directory. The query result cache stores all
eligible matches, so a later larger limit can reuse it without another search.

Search requests use `videoDuration=short`, the last 180 days, English relevance,
view-count ordering and up to 25 candidates. A single statistics/details request
then filters to durations up to 180 seconds and ranks by views per day (minimum
age denominator: one day). YouTube's short-duration search is an approximation;
duration alone does not establish a video's official Shorts classification or
visual format. Deleted, live, old and malformed entries are skipped.

Each uncached lookup conservatively reserves 101 quota units before either
request. Failed or empty searches retain that reservation. The JSON ledger uses
thread and OS process locks plus atomic writes. `RESEARCH_DAILY_UNIT_BUDGET`
defaults to 8000, resets by UTC day, and is shared by processes using the same
cache directory. This local guard does not account for other applications using
the same YouTube key; provider-side quota exhaustion is also handled with a safe
message. Keep the quota ledger when restarting or deploying if its budget must
persist. An invalid ledger fails closed. Multi-host deployments need a shared
quota store. Cached results consume no further HTTP calls or quota reservations.

## Clip grading

- `POST /api/projects/{pid}/clips/{jid}/{index}/grade` with `{ "use_edits": true }`
  returns 202 and a feature `job_id`, or a cached grade immediately with 200.
- `GET /api/features/{job_id}` reports progress and the completed `grade`.
- `GET /api/projects/{pid}/clips/{jid}/{index}/grade` returns the latest grade
  matching a current raw/edit state, or 404. Optional `use_edits=true|false`
  selects a particular mode.

The grader samples start/middle/end JPEGs inside the chosen trim, reads the
trimmed captions/transcript and manual text corrections, and includes caption,
composition, B-roll and other saved edit settings plus the session prompt. It
uses the editor's same media retrieval helper for local or S3-only clips. Frames
show base footage; captions, effects and B-roll are described as intended edits,
not falsely presented as rendered pixels. Comparable Shorts supply title,
duration and views/day metadata; the judge is told not to invent observations
about their visual or caption styles. Grades are qualitative guidance rather
than measured predictions of popularity.

The structured response supplies 0–10 ratings. Code computes the integer score:
`10 × (.30 hook + .15 pacing + .15 length_fit + .15 clarity + .10 captions + .15 trend_fit)`.
Fixed bands are A >=90, A- >=85, B+ >=80, B >=75, B- >=70, C+ >=65,
C >=60, C- >=55, D >=50, F below 50. Invalid rubric values are rejected.
The model is asked for 3–5 editable suggestions; unsupported action hints are
removed rather than executed. Trim, captions and B-roll hints use current editor
chat names. `aspect_ratio` and `pick_different_moment` are manual UI hints because
those operations have no supported editor chat action in the current backend.
These endpoints do not apply edits automatically.

Each clip stores `research/{index}/grade.json` in its job folder. Keys include the
clip identity, grading version, raw/edited mode, clip metadata and exact draft
state (not chat history). The raw grade and up to fifty recent snapshots are
retained. Draft changes invalidate edited grades without removing raw badges.
Queued jobs grade the draft snapshot captured at submission. Duplicate pending
requests reuse their feature job. All routes and source clips are ownership-checked.

## Wave batching and automatic grading

`POST /api/projects/{pid}/generations/{job_id}/grade` queues a wave grade, returning
409 while the wave is unfinished. All raw clips share one similar-Shorts lookup;
only uncached clips receive a judge call. Fully cached waves make neither lookup
nor model calls. Progress identifies the current clip. Empty waves return no best
clip and do not query YouTube.

The existing generations list includes each clip's raw `grade: {score, letter}`
or null. `best_clip_index` is set only when every clip in the wave has a cached raw
grade; ties choose the first clip. Grading never changes media or the generation's
successful state.

`AUTO_GRADE_WAVES=1` enables background grading after either agent or local-search
generation completes. It defaults off because grading can spend model tokens and
YouTube quota. An auto-grading queue failure is logged without failing the media
job. The backend only supplies grade data; badge UI is separate frontend work.

## Verification

```sh
python -m unittest tests.test_research_similar tests.test_research_grader -q
```

Tests use small YouTube JSON fixtures and mocked provider calls. They cover
quota concurrency/expiry/failure, cache hits, score math, letter bands, action
filtering, edited state snapshots, ownership, batching, partial grade badges,
background failures and default-off auto-grading. A media smoke check uses real
FFmpeg/FFprobe to sample a trimmed clip. Live provider usefulness and a sub-30-second
end-to-end grading latency are not established by these offline checks.
