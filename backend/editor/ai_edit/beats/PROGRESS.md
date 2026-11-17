# AI Editor "beats" build: progress

Branch: `ai-editor-beats` only. One commit per stage. Check `git branch --show-current` before every commit.
Engine switch: `CASCADE_EDIT_ENGINE=beats` (Cinema stays the default and is untouched).

## Status

| Stage | State | Commit |
|---|---|---|
| 0 Explore | done | (report only) |
| 1 Transcription | done; real-video check passed (Parakeet: 493/493 words, 100 % within 0.3 s) | Stage 1 commit + Parakeet engine in Stage 4 commit |
| 2 Director + critic | done offline; **live model runs blocked** (see Blocked) | Stage 2 commit |
| 3 Chat integration | done | Stage 3 commit |
| 4 Remotion renderer | done: example plan renders end to end (2680/2680 frames, worst beat start 0.4 frame, audio offset 0 ms, 627 s on 2 CPUs; one changed beat re-renders 2 beats in 97 s) | Stage 4 commit |
| 5 Real assets | done: speaker cut-outs (U^2-Net, cleaned for the mic-arm / fast-hand case), Pexels search + ranking + cache (blocked here, generated backgrounds used), 15 synthesized sound effects mixed under the speech at -14 LUFS | Stage 5 commit |
| 6 Polish vs reference | done: 3 rounds (see below); final edit `output/final_edit.mp4` + `output/REPORT.md` (gitignored) | Stage 6 commit |

## Blocked here (run on the Mac)

1. **Anthropic API: the key in `.env` is rejected** (`401 invalid x-api-key`, checked against
   https://api.anthropic.com directly). Live `make_plan` / `revise_plan` runs and director-prompt tuning need a
   valid key. The final video therefore uses the kit's validated plan (`examples/edit_plan_example.json`, made for
   this exact video and window). Once the key works:
   ```
   .venv/bin/python -m backend.editor.ai_edit.beats.service --window 27.12 71.78 --out /tmp/plan_fewshot.json
   .venv/bin/python -m backend.editor.ai_edit.beats.service --window 27.12 71.78 --no-example --out /tmp/plan_zero.json
   ```
2. **Pexels is unreachable from this sandbox** (egress proxy refuses api.pexels.com / videos.pexels.com). The
   Pexels path is built and tested offline; here b-roll beats use the renderer's generated motion backgrounds.
   On the Mac (with `PEXELS_API_KEY` in `.env`) real clips are used automatically.
3. **Hugging Face is unreachable here**, so faster-whisper cannot download its model; transcription used the
   Parakeet model (a GitHub release) instead. On the Mac, faster-whisper works as before.

## Decisions (made without asking)

- Inputs: the attached `final_demo.mov` / `inspo.mov` are the source and reference (copied to
  `examples/source/source.mov` and `reference/inspo.mov`, both gitignored).
- Plans live in `state.ai_plan`; once a version is rendered, `state.ai_edit` points at its film so the existing
  Edited preview and Export play it. Undo restores both.
- Renders go per beat with `npx remotion render <bundle> Edit --frames=a-b`; a beat's cache key covers the beat
  and the one before it (transitions draw the previous beat's tail), so a revision re-renders only changed beats
  and the beat after each. Segments are joined without re-encoding, then audio is muxed.
- Text behind the speaker uses Cinema's U^2-Net matte; the mic and arm stay in the cut-out (they are in front).
- Sound effects are synthesized (no sample packs), mixed under the speech, loudness -14 LUFS.

## Stage 4 results (this sandbox: 2 CPUs, Chrome 143, Remotion 4.0.543)

- Gate: KINETIC_KEYWORD built first; 3 beats rendered at 60 fps (144/105/82 frames = plan) and compared with
  reference frames (blur-to-sharp entrance, glow, whip/glitch transitions working; gaps noted for Stage 6).
- Full render of `examples/edit_plan_example.json` over `examples/source/source.mov`: `checks.ok = true`.
- All 10 templates and 6 transitions render; stills of every template were checked by eye.

## Stage 5 results

- Cut-outs: 237 frames for beats 1, 5, 16, 21 in 218 s. Mic-arm case checked on a magenta background: the speaker,
  hands, watch and mic head are kept; the teal arm drops out; stray hand fragments and half-transparent ghosts
  (from fast gestures) are removed by `assets.clean_matte`.
- B-roll: the real Pexels call was made with the `.env` key and refused by this sandbox's network ("Could not reach
  Pexels"), so all 10 b-roll subjects used generated motion backgrounds (no placeholder blocks).
- Render with assets: only the 8 affected beats re-rendered (407 s); `checks.ok = true`.

## Stage 6 rounds

1. Cut-out speaker + rim glow + ghost word on dark keyword beats; brighter B&W grade; huge stacked text behind the
   speaker with a red label; full-bleed light b-roll; filled glowing icons. (1681 s render)
2. Text-behind word kept readable (left two-thirds); two-word keywords stack; lighter vignette. (1354 s)
3. Generated b-roll stand-ins: soft focus + lens vignette, per-card tints, a better planet. (1477 s)
Stopped: remaining differences are footage (Pexels blocked here) and plan choices, not template style.
Final: 2680/2680 frames, worst beat start 0.4 frame, audio offset 0 ms, -14.9 LUFS.

## What is next

- Run the Step 0 model commands with a valid key; tune `prompts/director_prompt.txt`.
- Render on the Mac with Pexels (`python -m backend.editor.ai_edit.beats.make_example`).
- Click-to-edit beat rows in the chat UI (route exists); 9:16 template layouts; FCPXML export.

## How to run it on the Mac

One-time setup (repo root):
```
npm --prefix remotion ci                      # the renderer (Remotion downloads its own headless Chrome on first render)
.venv/bin/pip install -r requirements.txt     # already has faster-whisper, onnxruntime, anthropic
```
`.env` (restart the backend after changing it):
```
CASCADE_EDIT_ENGINE=beats          # use the beats engine for new AI edits (Cinema stays the default without it)
AI_EDITOR_MODEL=claude-sonnet-5-5  # any Anthropic model id
ANTHROPIC_API_KEY=...              # must be a valid key (the current one is rejected: 401)
PEXELS_API_KEY=...                 # b-roll; without it b-roll beats use generated backgrounds
# optional:
# CASCADE_BEATS_RENDER=off         # plans only, no video
# CASCADE_REMOTION_CONCURRENCY=4   # parallel frames per beat render
# CASCADE_REMOTION_BROWSER=/path/to/chrome
# CASCADE_TRANSCRIBER=parakeet     # force a transcriber (whisper-cli | faster-whisper | parakeet)
```
Run the app: `.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` and
`npm --prefix frontend run dev`, open http://127.0.0.1:5173, upload a clip, AI Editor tab: "Edit this video",
then "make it faster", "undo your last edit".

Render the example without the app (no model needed, uses the kit's validated plan):
```
.venv/bin/python -m backend.editor.ai_edit.beats.make_example
```
Compare with the reference:
```
.venv/bin/python -m backend.editor.ai_edit.beats.compare --ref backend/editor/ai_edit/beats/reference/inspo.mov \
  --ours backend/editor/ai_edit/beats/output/final_edit.mp4 --plan backend/editor/ai_edit/beats/examples/edit_plan_example.json \
  --out backend/editor/ai_edit/beats/output/side_by_side
```

## Planner provider and the demo clip (on demo-mock)

- `AI_EDITOR_PROVIDER=openai` plans with OpenAI (`OPENAI_API_KEY`, model `AI_EDITOR_OPENAI_MODEL` or Cascade's
  default OpenAI model); `anthropic` uses `AI_EDITOR_MODEL`. Unset: Anthropic if its key is set, else OpenAI.
- `demo.py`: when a clip contains the demo podcast's 27.12-71.78 s speech, the kit's validated plan is moved onto
  the clip's word times. Used when the planner cannot answer, and always with `CASCADE_BEATS_DEMO_PLAN=on`.

## Resume

```
git checkout ai-editor-beats
npm --prefix remotion ci
.venv/bin/python -m pytest tests/application/test_beats_*.py tests/application/test_cinema.py tests/application/test_ai_edit.py
npm --prefix remotion test
```

## Sound and pacing (demo-mock)

- Score: every render now has a dramatic, serious music bed (`beats/music.py`: D minor low strings, ostinato, taiko
  drums on the bar and a big drum on each impact beat), ducked under the voice by `cinema/score.mix`, -14 LUFS.
  `CASCADE_BEATS_MUSIC=off` leaves it out.
- Effects: all dark (air, drums, booms, rumbles, noise risers); tonal sine risers and shimmers removed. Effect names
  the director invents map by what they contain (`deep_rumble`, `low_hit`, `counter_tick`, ...).
- Pauses: `beats/tighten.py` cuts gaps longer than 0.3 s between words before rendering and drops empty "pause"
  beats. The saved plan is unchanged; the render uses the tight plan over a joined source. `CASCADE_BEATS_TIGHTEN=off`
  keeps pauses. Checked with a real render of beats 12-17 of the example plan (2.5 s of 8.3 s cut, frames and
  audio verified).
- A bare "render" / "render it again" in the chat re-renders the current version without calling the planner.
