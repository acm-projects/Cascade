# Reframing performance: measurements and implementation

All measurements below use the same local person, dog, selected-object and conversation files as the earlier tracking verification. No provider APIs or mocked inference were used for the timing runs.

## Hardware and method

- Apple M4 Pro, 14 CPU cores, 24 GiB unified memory; macOS ARM64. OpenCV 5.0.0 and PyTorch 2.14.0.
- Both versions ran sequentially with normal hardware access, explicit CPU FP32 inference, and cProfile enabled. Each version completed one initial cycle and two warm cycles. The table reports the median of those two warm observations; this is a small local benchmark, not a throughput SLA.
- Downloads, browser startup and HTTP setup are excluded. Video preparation, decoding, model work and crop planning are included. Input hashes and every observed time are in [reframe-benchmark-results.json](reframe-benchmark-results.json).
- Preliminary overlapping runs were discarded; they showed CPU contention. Only `/tmp/cascade-perf-report-before` and `/tmp/cascade-perf-report-after` feed this report.

## End-to-end processing

| Fixture | Media duration | Before | After | Speedup | Warm observed ranges, before / after |
|---|---:|---:|---:|---:|---|
| Person | 5.00s | 3.674s | 2.200s | 1.67× | 3.650–3.698s / 2.199–2.200s |
| Dog | 4.83s | 3.270s | 1.651s | 1.98× | 3.255–3.285s / 1.635–1.667s |
| Object | 1.20s | 2.498s | 2.073s | 1.21× | 2.491–2.505s / 2.069–2.077s |
| Conversation | 12.04s | 8.023s | 6.612s | 1.21× | 7.916–8.129s / 6.566–6.657s |

Initial-cycle totals (before → after) were person 4.673s → 2.325s, dog 3.271s → 1.665s, object 2.489s → 2.092s, conversation 7.921s → 7.415s. Import/model initialization occurs lazily, so a cold conversation can pay initialization costs that an earlier non-speaking clip skipped.

## Where the time went

Each cell is **before → after**, in seconds, using warm medians. Baseline stages come from cProfile and preparation-call timers; optimized stages use built-in wall-clock timers. Baseline active-speaker time includes batch bookkeeping. Tracking includes subject association/flow and manual MIL updates; optimized tracking also counts face-box association. Decode, miscellaneous Python work and model initialization are residuals, so these columns do not sum exactly to total time.

| Fixture | Video prep | Object detection | Face detection | Active speaker | Tracking | Crop planning |
|---|---:|---:|---:|---:|---:|---:|
| Person | 0.0657 → 0.0650 | 1.1601 → 1.2022 | 0.6284 → 0.6199 | 0.0009 → 0.0000 | 1.7383 → 0.2865 | 0.0005 → 0.0006 |
| Dog | 0.0555 → 0.0543 | 1.1561 → 1.1937 | 0.5301 → 0.0000 | 0.0009 → 0.0000 | 1.4505 → 0.3799 | 0.0006 → 0.0006 |
| Object | 0.0364 → 0.0381 | 0.2744 → 0.0000 | 0.1075 → 0.0000 | 0.0003 → 0.0000 | 2.0188 → 2.0230 | 0.0003 → 0.0003 |
| Conversation | 0.0971 → 0.0999 | 2.8457 → 2.8806 | 1.3333 → 1.3286 | 1.1949 → 1.1631 | 2.3218 → 1.0418 | 0.0014 → 0.0014 |

Audio preparation was approximately 0.026–0.036s before. It is now skipped for known silent media and non-speaking focus profiles; conversation audio preparation remains about 0.036s. Video preparation and planning were already small, so they were not replaced with a more risky decoding or planning implementation.

## Implemented changes

1. `backend/subject_tracking.py`: crop feature-extraction work to each subject ROI with a three-pixel gradient neighborhood, retaining the original mask, corner budget and thresholds. Batch all subjects into one forward/backward optical-flow call per frame rather than rebuilding pyramids per subject. Detector cadence and 640-pixel inputs are unchanged.
2. `backend/reframe.py`: choose a capability profile. Manual selections run MIL only; object-focused Auto runs YOLOX/flow; left/right/both run faces and bodies without speaker inference; conversation-capable Auto/Speaker preserves YuNet and Light-ASD. Silent clips skip audio preparation, and batches with at most one visible face skip unnecessary speaker scoring. Audio embeddings are reused between faces within a speaker batch.
3. YOLOX, YuNet and speaker models are cached by file revision. Mutable OpenCV models have inference locks. OpenCV uses four worker threads for these small inputs, avoiding oversubscription. Model loading remains lazy.
4. Manual selections seek to the selection time rounded down to the 25 fps grid, skipping prefix processing; prefix observations retain source timestamps and stable framing. The remaining clip is analyzed so later trim changes can reuse it. Auto/conversation analysis retains full context for identity and speaker hysteresis.
5. `backend/editor_backend.py`: deterministic owner/clip-scoped cache identity includes source/per-clip revision, context, capability profile, selection time/box, engine/OpenCV version and relevant model/device revisions. Output aspect ratio, caption style, B-roll and other downstream edits do not invalidate raw analysis. Manual selections ignore irrelevant context/model/device changes. Cached JSON is reused by file revision.
6. Identical queued/running requests share an analysis ID. A thread lock and OS file lock prevent duplicate inference across threads and local worker processes on macOS/Linux. Interrupted workers can be retried. Old engine results and changed media/models are rejected at plan/export time.
7. `web/editor_reframe.js` revalidates the analysis cache before preview/export preparation. Progress updates at least once per second of analyzed video. Cancel is enabled and preview playback remains available during preparation; conflicting edits remain locked. Cancelling stops the view from waiting, while a backend job may finish and be reused.

## Quality checks and retained limits

- Person, dog and conversation crop trajectories were identical to the baseline on these fixtures, including speaker switching and maximum crop steps. Resolution, detection frequency, confidence thresholds, source timing and smoothing limits were preserved.
- MIL is stochastic. In the selected-object warm comparison, maximum horizontal trajectory difference was 0.013964 of the available pan range (about 3.88 source pixels). All 30 frames retained manual-region observations; maximum crop step did not increase.
- An independent check of white foreground bounds in the six simple bag frames retained at least 95.2% of their horizontal span after, versus 95.5% before; the remaining frames were fully contained. This is a short visibility check, not general object-tracking ground truth.
- An attempted repeated-frame/MIL-update shortcut was rejected because it changed the manual trajectory more. Production manual analysis retains the original compression inputs and update cadence.
- Real browser tests check click/box selection, per-clip isolation, undo/redo, reload, conversation switching, B-roll, preferences and downloads. Preview/export tests compare rendered frames; the selected-bag check remains below its RGB-difference threshold, and the conversation comparisons passed.
- Natural conversation accuracy, long occlusions, crowded identity crossings and broad category accuracy remain unverified. No universal accuracy claim follows from these four fixtures.

## Acceleration policy

CPU remains the default. `CASCADE_REFRAME_DEVICE=auto` selects available CUDA/MPS, `mps` or `cuda` explicitly requests one, and `cpu` forces CPU. Unsupported or failing accelerator execution falls back to FP32 CPU; subsequent calls avoid a failed device. CUDA is implemented but untested on this Apple machine.

In a separate sequential same-environment conversation comparison, CPU warm runs were 6.424s and 6.373s; actual MPS runs were 6.262s and 6.293s. Both produced the same crop path. This roughly 2% end-to-end difference is too small to advertise as a meaningful GPU speedup, so MPS is opt-in. Restricted execution that reported MPS unavailable also completed using CPU.

## Reproduction and diagnostics

```sh
CASCADE_REFRAME_MODELS=/tmp/cascade-reframe-models CASCADE_REFRAME_DEVICE=cpu \
  python3 scripts/benchmark_reframe.py --fixtures /tmp/cascade-tracking-fixtures \
  --output /tmp/cascade-perf-new --runs 3
python3 scripts/compare_reframe_benchmarks.py /tmp/cascade-perf-report-before \
  /tmp/cascade-perf-new --output /tmp/cascade-perf-comparison.json
python3 -m unittest tests.test_reframe_cache tests.test_subject_tracking tests.test_reframe -q
```

The pre-change source snapshots are retained at `/tmp/cascade-perf-before`; the benchmark script accepts `--baseline` pointing there. Temporary files are not permanent repository assets. Public footage sources and setup are documented in [subject-tracking.md](subject-tracking.md). The baseline is engine version 2; optimized analysis is version 3.

Analysis records include phase timings/call counts and the actual speaker device. The authenticated job-status endpoint exposes those summaries without returning frame arrays. `tests/test_reframe_responsiveness_browser.py` passed playback/cancellation during real inference, cancellation/rejoin sharing one job, undo/redo and profile skipping. Ten ready-cache requests measured 1.31 ms median over local HTTP, with no model rerun (raw samples: `/tmp/cascade-perf-cache.json`). A selection at 2.5s was separately checked to skip prefix processing while retaining source timestamps.

Remote S3 clips are treated as immutable generation assets: their bucket/key and any supplied ETag/version participate in identity. Replacing an object externally under the same key without updating metadata is outside this cache contract. Unrelated result metadata, caption edits and changes to other clips do not force reanalysis.
