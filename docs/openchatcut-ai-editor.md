# AI Editor chat: OpenChatCut + Gemini free tier

The Editor page's **AI Editor** chat plans an edit with **one Gemini API free-tier request** and executes it with **OpenChatCut 0.2.17** (open-source editor engine). Everything runs at $0: no billing, cards, credits or paid fallback.

## How a request flows

1. **Plan (1 request).** The backend sends Gemini a compact context. It includes speech-safe candidate shot windows, measured music beats, one contact sheet of sampled frames, the transcript, the existing sequence and chat history, and a fixed menu of OpenChatCut assets verified to exist (zoom styles, transitions, look, grain, framing, title). Gemini returns a bounded JSON plan.
2. **Validate.** Cascade validates the plan, snaps cuts to beats and enforces limits: at most 3 transitions, 2 impact shakes and 1 slow-motion shot, and speech is never cut or sped up. It then saves the plan in the clip's normal `Edit` (`state.fablecut`, engine `openchatcut-0.2.17`). The plan feeds chat, timeline sequence cards, undo/redo and autosave.
3. **Execute.** For the Edited preview and export, the driver (`backend/editor/openchatcut_driver.mts`) applies the whole plan to a fresh OpenChatCut project in one offline edit session, with no browser, OpenChatCut agent or network. It commits atomically, then renders with OpenChatCut's own export pipeline. The MP4 is checked (streams, size, duration) and cached by edit state, so preview and export are byte-identical.

Follow-ups such as "less shake", "less zoom", "move the last zoom earlier", "remove shot 2", "remove the music" and "undo your last edit" use **no** request. Other montage follow-ups revise the existing sequence with one request. Small edits such as caption color or trims use one request in Gemini JSON mode against Cascade's action schema.

## Setup

```sh
python3 scripts/install_openchatcut.py   # pinned commit, npm ci --ignore-scripts
```

Requirements: Node 24, Google Chrome (or set `CASCADE_OPENCHATCUT_CHROME`), and ffmpeg/ffprobe (Homebrew). Put a free-tier key in the backend `.env` as `GEMINI_API_KEY`, created in Google AI Studio in a project **without billing**. Restart the backend.

With the key and engine present, the editor uses this path automatically. `CASCADE_EDITOR_PROVIDER=ollama` (or `openai` or `anthropic`) still selects the previous paths. `CASCADE_EDITOR_GEMINI_MODEL` may choose another allowlisted free model.

## Free tier and data use (verified 2026-11-02)

- Allowlisted models (free, tool/structured-output capable): `gemini-3.6-flash` (default), `gemini-3.8-flash`, `gemini-3-flash-preview`, `gemini-3.5-flash-lite`. Paid-only models are refused.
- Observed free quota: **20 requests/day per model** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), resetting at midnight Pacific. The chat shows Cascade's own count. A daily-quota error stops immediately with the reset time and changes nothing. A short per-minute limit is waited out once.
- When a model is overloaded (503), Cascade tries the next model on the free allowlist. It never routes around a daily quota.
- Google may use free-tier inputs and outputs to improve its products, and human reviewers may read them. Don't send sensitive or personal footage. Users must be 18+.

## Key protection

`GEMINI_API_KEY` is read only by `backend/editor/gemini_planner.py`, from the backend environment, and sent as a request header. It is never logged, returned by `/ai-status` or chat responses, placed in `VITE_` variables, or passed to OpenChatCut. The OpenChatCut subprocess gets an allowlisted environment without Cascade secrets.

## Licensing

- OpenChatCut is AGPL-3.0-or-later. It runs unmodified as a separate local engine; if you modify it and offer it over a network, publish the modified source.
- Its export uses Remotion, which is free for individuals, not-for-profits and companies with up to 3 employees. A larger for-profit company needs a Remotion company license.

## Limits

- Gemini sees sampled frames and the transcript, not continuous video. Shot choices can be imperfect, so review the cards and preview.
- Speed changes are constant per shot (no ramps or optical flow), and slow-motion action audio is muted.
- Captions use existing cue timing with estimated word grouping, not forced alignment.
- 2.4:1 footage cropped to 9:16 is capped at 2.4× enlargement; a blurred fill covers the remainder.
- No masks, tracking, generative media, reverse or freeze-frames.
- A render takes about 1–2 minutes the first time; cached afterwards.
- With 20 free requests a day, expect roughly 15–20 AI requests per day per model.
