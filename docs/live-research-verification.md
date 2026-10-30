# Real research failure diagnosis and verification

All work remains uncommitted on local `mlk`. Existing work, `.env` and
`.local-https/` were preserved. No external publishing/account actions occurred.

## Confirmed cause

The loaded application configuration has `DEEPGRAM_API_KEY`, `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY`, but **no `YOUTUBE_API_KEY`**. YouTube OAuth client credentials
are present; they are not a YouTube Data API developer key. The old discovery
function raised `RuntimeError("YOUTUBE_API_KEY is not set")`. The research adapter
caught that twice, discarded the underlying errors, and returned the generic
“No YouTube references could be analyzed” message. This was a discovery failure,
not evidence that transcription or the AI model was unavailable.

The configured OpenAI model (`gpt-6-luna`) answered a real structured request.
Actual reference transcription, tagging and synthesis also succeeded, so these
credentials were verified beyond a presence check. Secret values were never logged.

## Fixes

- Preserve real Data API discovery when a key is configured. With no key, use the
  existing yt-dlp package for **real public YouTube discovery**, verify individual
  upload dates, reject undated/older/over-ten-minute references, and retain source
  URLs, dates and the discovery-provider label. Public dates have day precision.
- If the exact content query finds no recent examples, retry a broader dialogue
  editing query and disclose the initial coverage gap. Do not replace dates or
  invent reference videos. Public search has a bounded candidate budget and may
  still be blocked by YouTube independently of Data API access.
- Add stage-aware, sanitized logs for discovery/metadata, download, FFmpeg frames,
  audio extraction, transcription, AI tagging/tutorial analysis and synthesis.
  Per-reference diagnostics distinguish configuration/authentication, quota/credit,
  rate limits, unavailable videos, bot challenges, format failures, timeouts,
  extraction, transcription, model availability and AI failures.
- Preserve successful references after other failures, including when final AI
  suggestion synthesis/validation fails. Surface retained sources and failure
  details in Trends. Do not log raw signed URLs, authorization or secret values.
- Replace silent yt-dlp duration-filter skipping with an explicit
  `reference_too_long` error. An initial diagnostic reference exceeded 600 seconds
  and previously yielded a misleading missing-file message.
- Configure the already-installed Node runtime for yt-dlp. The environment lacks
  the optional EJS solver distribution; YouTube emitted challenge warnings, but
  the validated references still downloaded successfully. No dependencies or secret
  configuration files were changed.
- Invalidate earlier generic-error cache versions. If research fails, chat now
  explicitly says **FALLBACK MODE — not trend-grounded** before reporting any local
  edits. A failed analysis is never described as current trend grounding.

## Why “flashy” looked restrained

Previously every request used the same style: at most three zooms, 2.5-second
spacing, 1.02→1.16 scale, one 0.003 shake, four-word size-50 pop captions, and one
quiet whoosh. The natural-language adjective did not select a stronger profile.

The flashy/crazy request now selects a saved `intensity=flashy` profile:

| Setting | High-energy default | Flashy |
|---|---|---|
| Zoom budget | 3 | 6 |
| Zoom scale | 1.04→1.24 | 1.06→1.38 |
| Minimum event spacing | 2.5s | 1.25s |
| Zoom duration | 0.7s | 0.45s |
| Shake | first event, 0.004 | first two events, 0.009 |
| Captions | four-word size-50 pop | three-word size-60 animated karaoke |
| Sound accents | quiet whoosh | whoosh + quiet final impact if room |

Events snap to measured music beats and dialogue cues, spread across the clip,
and protect spoken phrases. Speech is not sped up. Music/SFX stay ducked. It does
not add arbitrary strobes, masks, glows or unsupported effects. Missing/spacing-
blocked stock remains a failed/skipped step, not an insertion claim.

## Real verification

Ran `scripts/demo_live_trends.py` on an isolated copy of the existing Teddy clip.
Only local identity/project storage are fixtures; **YouTube discovery, downloads,
Deepgram, OpenAI analysis/synthesis and Pexels were real**. No provider result was
mocked. The completed research returned these analyzed examples:

- https://www.youtube.com/watch?v=Jhs4vL3f5GM — Heath-Hardy-Dialogue-Edit-Assignment
- https://www.youtube.com/watch?v=RFsHtewjKn8 — Dialogue Edit by Joey Ellis

Both returned upload day 2026-10-16. No eligible tutorial passed the recent/date/
duration filters in this run; the report retains that coverage gap. This is a
small YouTube-based comparison, not verified TikTok/Instagram market trends.

The final effect-spacing improvement reuses this same fresh real report after
checking identical original-media SHA-256 and edit fingerprint. It avoids redundant
paid research calls; it does not replace analysis with a fixture.

Final files: `/tmp/cascade-real-flashy-final/original.mp4`, `edited.mp4`,
`research.json`, `execution.json`, `verification.json`, and matched-frame images.
The earlier fresh end-to-end run is `/tmp/cascade-real-flashy-v2/`.

To repeat with actual configured services (incurs normal service use):

```sh
CASCADE_WARM_MODELS=0 .venv/bin/python scripts/demo_live_trends.py /tmp/my-new-real-research-demo
```

Use a new directory; existing output is never overwritten. The source fixture is
the existing local Teddy clip. The script saves/reloads the resulting draft and
exports through the production renderer. A failed research run returns exit code 2
and labels any rendered local style as fallback. No secret-file changes are needed
for the verified public-search path; configuring `YOUTUBE_API_KEY` opts into the
existing Data API implementation.

Offline regression checks:

```sh
CASCADE_WARM_MODELS=0 .venv/bin/python -m unittest tests.test_clip_trends tests.test_trend_diagnostics tests.test_high_energy_reel tests.test_advanced_editing tests.test_editor tests.test_broll -q
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run lint
```

Frame/audio verification supplements these tests: matched source/output frames,
real captions/zoom/stock differences, decoded audio mix residual, dialogue waveform
correlation, peak level, and matching audio/video/output-clock duration. Subjective
listening and real browser voice playback remain manual checks.
