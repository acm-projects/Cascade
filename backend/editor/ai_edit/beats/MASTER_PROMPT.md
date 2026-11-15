# MASTER PROMPT: add the "AI Editor" to my app

You are a senior engineer working in my existing codebase. Build an AI video
editor: the user uploads a raw podcast video, chats with an AI, and gets back a
heavily edited short-form video in the style of the reference clip
(`reference/inspo.mov`): kinetic keyword typography, meaning-driven b-roll,
speaker cutouts with text behind them, scribble highlights, number counters,
whip/blur transitions, semantic colors, and sound design.

## 0. Ground rules
- **Explore first, don't assume.** Read the repo, find the existing "AI editor
  chat", and report: stack, how videos are uploaded and stored, how the chat
  works end to end, where background jobs run, and where I should hook in.
  Then give me a short plan and wait for my OK before large changes.
- Work in **stages** (section 4). Finish one stage, show me how to verify it,
  then continue. Never rewrite unrelated code.
- Secrets only from environment variables. Never hard-code keys.
- The LLM model name comes from an env var (`AI_EDITOR_MODEL`) so I can change it.
- Ask me ONE question at a time, only when blocked.

## 1. What's in this kit
```
prompts/director_prompt.txt   system prompt: transcript -> edit plan JSON
prompts/critic_prompt.txt     system prompt: QA a plan and return a fixed plan
prompts/revise_prompt.txt     system prompt: apply a chat request to an existing plan
examples/transcript_full.json real word-level transcript (Parakeet, ~175s)
examples/edit_plan_example.json  a validated plan for the 27.12-71.78s window
scripts/transcribe.py         reference: audio -> word-level transcript
scripts/critic.py             reference: rule validator (port it into the app)
reference/inspo.mov           the style reference (I will add it)
```
Treat `examples/` as the few-shot example and as the test fixture. Load the
prompts from these files (copy them into the app's own prompts folder) rather
than retyping them.

## 2. Architecture (one pipeline, the plan JSON is the source of truth)
```
upload -> extract audio -> TRANSCRIBE (word timestamps)
       -> DIRECTOR (LLM)  -> plan.json
       -> CRITIC loop (LLM + code validator, max 2 rounds)
       -> ASSETS (speaker cutout, b-roll, maps, screenshots, sfx)
       -> RENDER (Remotion, 60fps, motion blur) -> mp4 + editable timeline
chat message -> REVISE (LLM) -> patched plan.json -> re-render only changed beats
```
Rules for the LLM layer:
- Call the Anthropic API with the prompt files as the system prompt. Put
  `examples/` in as one few-shot user/assistant turn before the real input.
- Output must be valid JSON. Strip code fences, parse, then validate with the
  code validator (port `scripts/critic.py` into the app's language if needed).
  On failure, retry once with the validation errors appended; then surface a
  friendly error in the chat.
- Store every plan version (plan id, parent id, user message, score). This
  gives me undo/redo and an evaluation dataset.
- The renderer reads ONLY plan.json plus assets. No LLM calls inside rendering.

## 3. The AI editor chat behavior
- First message with a video: transcribe (show progress), pick the best 30-60s
  window if the video is long, run director + critic, show a compact beat list
  (time, on-screen text, template), then render a preview.
- Follow-up messages ("make the hook punchier", "less b-roll", "red for the debt
  part", "swap beat 7 for a counter", "faster") go to the REVISE prompt with the
  current plan. Apply the returned plan, show `reply` and which beats changed,
  and re-render only those beats.
- Users can also click a beat to edit its text, color, or template directly;
  those edits go through the same validator.
- If the user asks something outside editing, answer normally.

## 4. Stages (acceptance criteria for each)
**Stage 0: Explore.** Report findings and a plan. No code changes.

**Stage 1: Transcription service.** Audio extraction (ffmpeg) + word-level
transcription behind one function `transcribe(video) -> [{word,start,end}]`.
Use a Whisper-family model if the environment can run it (WhisperX /
faster-whisper), otherwise adapt `scripts/transcribe.py`. Accept: running it on
the example video yields timestamps within ~0.3s of `examples/transcript_full.json`.

**Stage 2: Director + critic service.** `make_plan(transcript, window?, instructions?)`
and `revise_plan(plan, transcript, message)`. Include JSON validation and retry.
Accept: on `examples/transcript_full.json` with window 27.12-71.78 the validator
reports 0 high-severity issues, and the plan resembles `examples/edit_plan_example.json`.

**Stage 3: Chat integration.** Wire stages 1-2 into the existing AI editor chat
as in section 3, with plan versioning. Accept: I can chat "make it faster" and
see a new plan version with only affected beats changed.

**Stage 4: Renderer.** A Remotion project that reads plan.json + source video.
Build templates in this order and show me a preview after each:
1. `KINETIC_KEYWORD`, 2. `BROLL_OVERLAY` (placeholder color blocks first),
3. `PLAIN_SPEAKER`, 4. `SCRIBBLE_HIGHLIGHT`, 5. `TEXT_BEHIND_SUBJECT`,
6. `SPEAKER_CUTOUT_ICONS`, 7. `COLLAGE`, 8. `NUMBER_COUNTER`,
9. `MAP_CALLOUT`, 10. `SCREENSHOT_CALLOUT`. Plus the six transitions.
Accept: `examples/edit_plan_example.json` renders end to end to an mp4 whose
beat timing matches the plan within 1 frame at 60fps.

**Stage 5: Assets.** (a) Speaker matting (Robust Video Matting or SAM2) for the
two cutout templates; the speaker is filmed in profile with a mic arm crossing
the frame, so test that edge case. (b) B-roll search from a licensed stock API
(e.g. Pexels), ranked by text similarity to `broll_query`, using
`broll_fallback_query` when needed; cache results. (c) Sound effects mapped from
each beat's `sfx` field using royalty-free files. Accept: no placeholder blocks
remain in the example render.

**Stage 6: Polish loop.** Put my reference clip side by side with the render and
tune until close: see the style bible below. Add export of an editable timeline
(FCPXML) if time allows.

## 5. Style bible (what "like the reference" means)
- Fonts: bold condensed sans for the keyword + italic serif for the accent word.
- Text entrance: starts blurred and scaled, snaps sharp within ~6 frames; soft
  outer glow in the beat's semantic color.
- Semantic colors: green = money/growth/life, red = debt/danger/controversy,
  yellow = creativity/music, orange = obsession/intensity, white = neutral.
- Alternate light "paper grid" backgrounds and dark scenes; subtle film grain
  and vignette; high-contrast black-and-white grade on serious beats.
- Transitions: whip pan, zoom blur, glitch, flash cut, slide, fade, with motion
  blur. Whoosh/impact SFX on cuts. A short riser into the biggest payoff line.
- Scribble highlight is hand-drawn with a stroke-reveal animation.
- Pace: a new visual idea every 1-2s. Keep text to 1-4 words.
- 60fps, aspect ratio from the source (add a 9:16 reframe option that keeps the
  speaker in frame).

## 6. Don'ts
- Don't copy the reference's watermark, footage, fonts you can't license, or
  any third-party clips. Use licensed stock or user-provided assets only.
- Don't call the LLM during rendering; don't skip validation of LLM output.
- Don't claim a stage is done without running its acceptance check and
  showing me the result.

Start with **Stage 0** now.
