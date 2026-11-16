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
| 6 Polish vs reference | not started | |

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

## Resume

```
git checkout ai-editor-beats
npm --prefix remotion ci
.venv/bin/python -m pytest tests/application/test_beats_*.py tests/application/test_cinema.py tests/application/test_ai_edit.py
npm --prefix remotion test
```
