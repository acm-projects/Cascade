# Four-clip investigation on manila/editor-work

HEAD and the local `origin/please-god-fix` reference both resolve to `40201e6177995d5e2786459efe62ec087944ed1c`. No branch operation, fetch/pull, stash operation or cleanup of pre-existing work was needed. The restored editor files remain present.

## Where the count dropped

The active canvas defaults to `engine=openai`, not local visual/speech search. Kashmine's commit changed `backend/video_search/router.py` and the local selection algorithm; those changes are present. The OpenAI scene selector is a different path.

The actual flow is:

1. `flow_C.js` posts the selected engine, source, prompt, project ID and preferred duration to `/upload` on the same origin.
2. `app1.upload_video` dispatches OpenAI to `process_openai_upload`, Ollama to `process_upload`, or local visual/speech to `integration.process_search`.
3. OpenAI proposes candidate moments; `openai_scene.choose_clips` validates their bounds, scores, duration and overlap. FFmpeg renders only the selected candidates, and `results.json` persists that exact list.
4. `/api/features/{job}` returns the full persisted/in-memory list without slicing it to one.
5. `showCanvasClip` iterates every returned clip, creates a card/video/radio, and passes the selected zero-based index in the editor link.
6. The editor lists real project results by session and loads the selected job/index. Opening one clip in the main editor is intentional; it does not discard the other results.

Saved job `7f74170ad08b45199aa950e7cd7a8cb3` proves the failure was at OpenAI boundary validation: **8 proposed candidates → 1 selected → 1 rendered → 1 in API results**. Seven high-scoring proposals were shorter than the eight-second minimum. Scores and source bounds passed; provider failure and canvas truncation did not explain this run. Its eight-second 23.8–31.8 candidate was the sole survivor.

Other saved responses showed the same issue:

| Saved job prefix | Proposed | Below minimum | Old selected | Corrected selected |
|---|---:|---:|---:|---:|
| `0bd125ed` | 10 | 10 | 0 | 4 |
| `b6f4e4c1` | 10 | 10 | 0 | 4 |
| `b1c65837` | 10 | 9 | 1 | 4 |
| `7f74170a` | 8 | 7 | 1 | 4 |

Older one-clip results from the legacy pipeline are also present. Git updates do not regenerate saved results. Returning to a canvas can restore an explicit `job` URL or saved job selection, so an old one-clip result remains one until a new generation is requested. Existing results were not rewritten.

## Fix

`openai_scene.py` now retains a supported short proposal by adding the minimum required surrounding context. Leading/centered/trailing placements are considered to avoid introducing unnecessary overlap. Every expansion contains the complete original supported moment and stays in the source. Score threshold 5, duplicate filtering, source bounds, maximum duration, non-overlap and the four-result limit remain enforced. One matched moment cannot become four copies. Sources shorter than eight seconds can use their full length. Generation prompts and the paid-response cache fingerprint are unchanged.

The result carries aggregate `selection_diagnostics` and a visible context note through the existing API/status path. New ownership records additionally retain engine, mode and target duration so future jobs have unambiguous provenance. No database migration is needed.

A separate machine issue affected local search: the default `/opt/homebrew/bin/ffmpeg` lacks the `subtitles` filter, while `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` has it. `video_tools.py` selects a compatible installed renderer for local-search caption burning. An explicit `CASCADE_FFMPEG` override is supported. If no compatible build is found, processing returns an actionable libass configuration error instead of a generic failed subprocess. No binaries, PATH, `.env`, or credentials were changed.

This pipeline promises **up to four distinct available matches**, not four on every input. OpenAI additionally requires supported scores; local search ranks the available embedding matches without a fixed score-5 cutoff. Legacy Ollama merges adjacent high-scoring observations and may return fewer. Short sources, overlapping moments, weak evidence or absent speech can legitimately yield fewer.

## Runtime and configuration

No relevant backend process or listener on port 8000 was running when checked, so the earlier live process cannot be identified retrospectively. The correct integrated entry point is:

```sh
python3 -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

`backend.app:app` is verified to alias the same application. Legacy `app.py`/`main.py` are not equivalent website entry points. Open the frontend from that backend origin, not a file URL or separate static server. Restart after applying this fix, then request a new generation. Compatible cached OpenAI proposals can be reused and revalidated; saved one-clip jobs are not automatically replaced.

OpenAI and Clerk key fields, AWS access/secret fields, `S3_BUCKET_NAME` and `AWS_DEFAULT_REGION` are configured. Optional OpenAI model/frame-count settings are unset and use their defaults. With storage mode unset and a bucket configured, the existing auto mode selects S3. Presence is not proof of current provider access or bucket permissions; no remote credential-validation call was made. Optional Anthropic/YouTube keys are absent and affect research, not four-clip generation. Cached CLIP, sentence-search and Whisper models are installed. No secret values were printed.

## Verification and limits

- Regression tests cover the actual short-candidate shape, context/source bounds, score rejection, duplicates, overlapping evidence, short sources and renderer capability fallback.
- Full automated tests use mocked paid providers/identity where applicable and real local FFmpeg/media/persistence. The default local FFmpeg PATH now passes the suite, including subtitle-rendering tests.
- **Real offline local visual generation:** the saved source from `7f74170a`, actual cached CLIP/Whisper models, prompt `a person speaking`, preferred duration 30s; produced **four real, non-overlapping 15-second videos** with audio/caption handling. No model output was mocked and no model download or paid API call occurred.
- **Real offline speech generation on that same source:** Whisper found no speech and correctly returned an explicit error. Its saved transcript is also empty. This is not a claim that every source can produce four speech clips.
- **Saved OpenAI response replay:** actual source and saved real proposal passed through `/upload`, real frame extraction, real FFmpeg rendering, actual API/persistence/media/editor routes, producing **four playable eight-second clips**. Identity, local storage selection and the provider-response boundary were replaced for this isolated test. This verifies the fix against real historical provider data, not a fresh live OpenAI generation.
- **Real Chrome canvas/editor check:** consumed those API results using the actual canvas/shared flow, displayed four playable card videos, selected radio 4, verified `clip=3`, and loaded **Session 1 · Clip 4** with four clips in the editor sidebar. Only test identity/startup bootstrap was replaced. No production authentication changes were made.

Reproduction helpers: `tests/replay_saved_generation.py`, `tests/replay_four_clip_browser.py`, and existing `tests/live_search_smoke.py`. Logs/artifacts for this investigation are under the temporary directory, not original job storage. Fresh paid OpenAI access, live Clerk and S3 delivery were not tested end to end.
