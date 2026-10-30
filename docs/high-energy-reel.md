# High-Energy Reel

Implemented in the existing React editor on local `mlk`; no redesign, commit,
merge, push, stash application, or publishing. Preexisting uncommitted work remains.

## Try it

From the repository root, start the existing backend:

```sh
CASCADE_WARM_MODELS=0 .venv/bin/python -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

In another terminal, start the existing React development server:

```sh
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173**, authenticate, open a project and a transcribed video
in Editor. Choose **Reel → Apply High-Energy Reel**, or send:

> Make this a polished high-energy Reel with a strong opening, beat-synced edits,
> bold animated captions, selective punch-in zooms, relevant B-roll, and music
> that stays beneath the dialogue.

Use **Original / Edited** to compare. Edited preview is a debounced server-rendered
MP4 using the same renderer as download. It can take time; the UI labels the source
while rendering and reports errors. Review the chat's per-action results. Music
controls, timeline, chat, undo/redo and autosave all share the same draft. Reapplying
the style replaces its effect arrangement. A request to keep the full duration
disables hook trimming and pause compression.

## What executes

- The AI receives actual transcript phrases, scene boundaries and bounded action
  schemas. A validated style action expands into exact timestamps, track/asset
  IDs, durations and settings; chat returns the fully resolved plan.
- A complete transcript phrase supplies the opening. Only trailing silence may be
  removed at the end. Kept ranges cannot split a spoken phrase.
- Music onset analysis measures a beat grid and confidence from the actual audio.
  Punch-ins and cutaway timing snap to that output-time grid. Silence gives no
  invented beat grid. Replacing/repositioning music flags the grid as stale.
- Up to three 1.02–1.16× punch-ins, one subtle shake, one brief blur at a scene
  boundary, short B-roll dissolves, entrance/exit fades, and restrained color.
- At most two pause-only speed ramps, with speech guards. Rates change in eight
  steps, not a continuous optical-flow ramp. Dialogue stays at 1×.
- Four-word pop captions, selected transcript keywords highlighted, estimated
  timing inside real cues. No forced word alignment.
- Real procedural Reel pulse music, one quiet whoosh, fades and cue-based dialogue
  ducking. Uploaded music uses the same private audio asset system and controls.
- Selective Pexels cutaways use content-grounded queries, preserve dialogue and
  retain attribution. Missing stock/provider access is reported; other edits stay.

The shared source/output clock maps captions, effects, audio, seeking and download
through cuts and ramps. Saved drafts persist this complete state. Ownership checks
remain on source clips, drafts and asset access. Undo history remains in-session;
saved edits persist across reloads.

## Demonstration and validation

The existing 36.83-second Teddy clip was copied into an isolated project. A real
configured AI response and Pexels search were used with the user's prior approval.
After correcting an irrelevant music-based stock query and bypassing unity-rate
audio time stretching, the validated live plan was replayed to render:

`/tmp/cascade-high-energy-reel-final.mp4`

Its report is `/tmp/cascade-high-energy-reel-final.report.json`. Output is 33.01s:
complete opening at source 3.12s, pause ramps at 23.46–24.77s and 30.93–32.25s,
measured ~120.2 BPM, punch-ins at output 3.00/6.50/13.00s, one blur at 10.50s,
and a teddy-bear cutaway at 23.00–24.00s. Frames were inspected for captions,
effects and relevant stock. Audio was decoded and checked for levels, duration,
speech waveform preservation and pitch; subjective listening remains a user check.

Tests cover measured beats versus silence, phrase safety, ramp rejection over
speech, partial failure, clock inversion, beat-aligned effects, save/reload,
ownership, actual retimed audio/video export and speech pitch. The isolated browser
test covers style application, Original/Edited tabs, rendered duration, undo/redo,
autosave and reload. Frontend build/tests/lint also run. No external posts are made.

## Requirements and boundaries

Use the existing AI provider configuration and Pexels key; no secret files were
changed. FFmpeg/ffprobe, numpy, the existing Python dependencies, and transcript
timestamps are required. The local music catalog needs no external music service.

Beat and hook quality are estimates, not human musical/semantic judgment. Stock
query grounding does not verify visual semantics: review inserted footage. The
style uses Fit composition; source-timed tracking/Fill is rejected with retiming.
It preserves the chosen aspect ratio rather than automatically cropping subjects
to portrait. Set the desired aspect ratio manually. There is no arbitrary masking,
glow, freeze-frame, reverse, generative footage, optical-flow ramp or exact reference
reproduction. Existing source shot cuts are not all moved onto beats. Preview needs
CPU/render time and persistent assets; it is not instant GPU compositing.

The existing dotenv loader reports an invalid statement at line 9 on this checkout.
Its contents were not inspected or rewritten; successful demo configuration already
worked. If your startup configuration fails, correct that statement privately.
