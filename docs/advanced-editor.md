# Natural-language editing and Music controls

The newer [High-Energy Reel](high-energy-reel.md) adds measured beat timing,
phrase-safe retiming, pause-only ramps, stock dissolves, blur accents and explicit
Original/Edited previews. Its scope and validation supersede the older limitations
below for those features.

Implemented locally on the existing **`mlk`** checkout, within the official React
editor. No branch creation, commit, push, merge, reset or stash application was
performed. Existing layout, navigation and theme tokens are preserved. Music is
an additional controls-panel tab; audio and effects appear as timeline tracks.

## What executes

The chat asks the existing configured AI provider for a bounded structured plan.
Each action has generated-clip timestamps, duration, asset references and settings.
The executor validates and applies one action at a time. A failed step is reported
without discarding successful steps. Search-only results are never described as
inserted footage. An explicitly authorized automatic insertion request upgrades
a legacy search-only plan into actual search/select/download/insertion.

- Automatic B-roll uses existing Pexels search and private clip-scoped asset
  registry. Suitable-duration results are tried until a downloadable candidate is
  found. Insertion preserves source dialogue, sits under captions and retains
  provider attribution in state. Non-overlap and clip bounds remain enforced.
- Music and SFX use owner/clip-scoped asset IDs, not model-supplied URLs or paths.
  Three actual synthesized music recordings (Tension pulse, Quiet reflection,
  Playful plucks) and three synthesized SFX (Impact hit, Air whoosh, Bell accent)
  are available. They are simple procedural sounds, not licensed commercial songs
  or generated orchestral performances. Names, previews and Add/Replace work.
- User uploads are probed and transcoded to private WAV assets. Limits: 50 MB,
  playable audio, 0.05 seconds–20 minutes. Only upload audio you can use. The Music
  tab adjusts position, source trim/offset, duration, volume, looping, fades,
  dialogue ducking and duck level; it can replace/remove music or add/remove SFX.
  Chat sees the same audio state and available uploaded/catalog asset metadata.
- Music ducks with attack/release envelopes around actual transcript speech
  windows. This is cue-based ducking, not real-time speaker/VAD or beat analysis.
  Missing transcripts mean no automatic speech ducking. Original dialogue volume
  defaults to 1 and can be changed explicitly through a plan.
- Timed punch-ins/interpolated zooms and bounded camera shake operate on the final
  video composition. Dialogue timing and overall clip length remain unchanged.
- Color brightness/contrast/saturation/grayscale, timed text overlays, clip
  entrance/exit fades, pop captions and progressive highlighted-word captions
  render through FFmpeg/ASS. Highlight timing is distributed within actual cue
  intervals; it is **estimated word timing**, not forced alignment.
- Local scene-cut detection supplies timing hints alongside actual dialogue cues,
  current edit state and clip metadata. It does not infer characters, emotions,
  visual semantics, punches or musical beats. Quoted dialogue anchors are checked
  against the real transcript before placement; nonexistent anchors fail visibly.

Duration changes are blocked unless explicitly requested. Negated trimming
requests ("do not trim", "keep the full clip") override a spurious model trim.
Short B-roll shot durations cannot authorize a shorter main clip.

## Preview, saving and export

Manual Music controls and chat both update the existing undoable edit state.
Autosave persists the full audio/motion/text state. Save status changes immediately
when an edit is pending; switching editor clips and using Go to Export flushes
pending edits first. An unsaved reload/close triggers a browser warning. Undo/redo
remains the existing in-session history; saved edits survive reloads, history itself
does not survive reloads. Save errors remain visible.

Advanced previews debounce an actual server render and play the returned encoded
MP4/MP3. The UI labels the original source while rendering and reports failures;
it does not pretend CSS approximations contain rendered B-roll/audio. Timeline
seeking maps back to generated-clip timestamps. This gives preview/export parity
but requires a render round trip, CPU and persistent source/media assets; it is
not an instant interactive multi-track GPU preview.

The existing MP4/ZIP/YouTube export paths retain the complete draft object and use
the same renderer. Added audio is mixed with dialogue, faded, ducked, padded/trimmed
to the chosen clip duration and limited to prevent clipping. Audio-only recordings
also support the new audio mix in their existing MP3 export path. Publishing was
not performed during this task.

## Reference inspection and boundaries

Inspected downloaded 0–10 second excerpts of the two supplied Shorts and retrieved
captions for the three longer tutorials. This is not a claim to have watched all
five full videos or performed an exact style transfer.

- `FWkWDsyCuIo`: the excerpt shows a CapCut layered overlay/shake transition
  demonstration, fast scale/position changes and punchy title text. Subject masking
  and layered custom transition composition are beyond the implemented punch-ins,
  shake and text/fade subset.
- `NBP29CgG3tQ`: the excerpt shows negative-space logo/headlight reveals, blue glow,
  dramatic pauses and a car reveal. Custom logo animation, glow compositing,
  masks, motion blur and exact beat synchronization are not implemented.
- `pdLEHfkwgV8`: retrieved tutorial captions emphasize simple cuts, music selection
  as a pacing/emotion reference and supporting sound design.
- `i_G9pE89jD8`: retrieved captions discuss brightness/contrast/color balance and
  the importance of the footage/lighting over a universal grading preset.
- `sLgHqZSe2o0`: retrieved captions discuss A/B-roll, punch-ins, sound accents,
  seamless cut decisions, transitions and music choice.

Still unsupported and reported as such: freeze-frames, speed changes/ramps,
reverse, generative video, exact word alignment, automatic musical beat detection,
subject masking/rotoscoping, glows/complex compositing, shot-to-shot custom wipes,
and exact reproduction of reference edits. Only whole-clip fade-in/out transitions
are implemented. A relevant stock search result is not a semantic visual guarantee;
review the chosen footage and the final exported cut.

## Teddy demonstrations

The actual local Teddy/John clip was copied into a temporary project, never edited
in place. Both demonstrations retained **36.828458 seconds**.

- `/tmp/cascade-teddy-local-demo.mp4`: deterministic mocked plan/search, real
  user-supplied cutaway, original dialogue, synthesized music/SFX and real render.
- `/tmp/cascade-teddy-live-demo.mp4`: after explicit user approval for outbound
  transcript/context and search terms, the configured AI + real Pexels applied 11
  steps. Cutaways appeared at 24.88–27.07s and 34.11–36.31s; music covered the full
  clip; impact at 14.07s, whoosh at 32.35s, motion events at 14.07s, 21.27s, 32.35s,
  highlighted captions, a TEDDY! overlay at 34.11s and clip fades.
- Corresponding `.report.json` files contain structured plans, actual per-step
  outcomes and the saved state. No credentials are included. These temporary
  artifacts are not committed or published. Intermediate demo assets are removed.

Export frames were decoded/inspected, actual MP4 durations checked, and audio
changes measured. Source-dialogue correlation in the live demo was 0.968 after
accounting for the limiter's then-default 5 ms latency; the renderer now compensates
that limiter latency. Added hits/whooshes produced clear energy increases at their
scheduled times. This is media/signal verification, not a claim that the creative
result equals the reference editors' work. Listen/review the delivered demo.

To repeat on a copy, without external calls:

```sh
.venv/bin/python scripts/demo_advanced_editor.py --source /path/clip.mp4 --captions /path/clip.vtt --cutaway /path/permitted-cutaway.mp4 --output /tmp/my-teddy-demo.mp4
```

`--live-ai` is explicit opt-in: it sends transcript/timing/edit context to the
configured AI provider and stock search terms to Pexels. Do not use it for private
media without permission. Never use a publishing endpoint to test edits.

## Configuration and verification

No environment file was read for display or rewritten. Existing AI provider
configuration is reused; `PEXELS_API_KEY` is needed for real automatic stock
search. Music/SFX catalog and local uploads need no external audio provider or key.
FFmpeg/ffprobe and FFmpeg libass support are required for audio/rendered captions;
existing `CASCADE_EDITOR_FFMPEG` can select the compatible binary.
The local environment loader reported an existing parse warning at `.env` line 9;
that file was left untouched. Check that line privately if configuration is missing.

Run normal frontend/backend startup as before; no website serving or design
replacement was introduced by this work.

```sh
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend test
CASCADE_WARM_MODELS=0 .venv/bin/python -m unittest tests.test_advanced_editing tests.test_editor tests.test_broll tests.test_audio_media tests.test_social_youtube -q
```

Tests cover multi-action execution, automatic insertion (including legacy
search-only plans), duration preservation/negation, failed asset partial success,
private uploads/ownership, persistence, visible B-roll/motion/captions/text, real
MP4 duration, music/SFX frequency energy, preserved dialogue and actual duck/fade
attenuation. Automated AI/Pexels calls are mocked. The one live demo was separately
approved. Frontend tests also preserve existing timeline/export behavior.

For isolated official-React browser checks, build first, then run in separate
test-only processes:

```sh
.venv/bin/python tests/advanced_editor_browser_server.py
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --remote-debugging-port=9351 --user-data-dir=/tmp/cascade-advanced-edit-browser --no-first-run about:blank
.venv/bin/python tests/test_advanced_editor_browser.py
```

This verifies Music list/preview/Add/Remove, undo/redo, chat-to-Music/timeline
synchronization, manual volume autosave/reload and server-rendered preview. Browser
screenshots are `/tmp/cascade-advanced-music-*.png`. The existing desktop-oriented
layout is preserved; the test does not establish a redesigned mobile layout.
