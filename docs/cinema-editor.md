# Cascade Cinema: the AI Editor's finished-edit engine

Type **"Edit this video"** in the Editor's AI chat and Cascade returns a finished cut: clean dialogue, a
story with a cold open and a payoff, full-screen b-roll, captions, an original score, a closing message
and the Cascade sign-off. This document is the map of how that works and how to keep building on it.

The design rule: **an AI model plans; Cascade's own code edits.** The plan is a small JSON document.
Everything that touches video or audio is deterministic Python and FFmpeg. So the editor does not depend
on any particular model, and a saved edit can be reopened, changed and exported with no model at all.

## How one edit flows

```
AI chat "Edit this video"
  -> backend/editor/chat.py            routes edit requests to the job runner
  -> backend/editor/ai_edit/jobs.py    _run_cinema(): one background job per clip
       1. prep.py                      word timings (whisper-cli, or faster-whisper), camera cuts, contact sheets (cached per clip)
       2. cinema/planner.py            asks the configured planner for a CinemaPlan      <- the only AI step
            cinema/prompts/director.md   what the planner is told
            cinema/plan.py               the plan's schema, its checks, and the rule-based director (no AI)
       3. cinema/engine.py             renders the plan                                  <- no AI
            speech.py     clean dialogue cut: fillers, false starts, pauses, crossfades
            speakers.py   removes the asker's interjections inside an answer
            render.py     framing, captions, giant words, b-roll, payoff, message (NumPy + FFmpeg)
            matte.py      person cut-out for words behind the speaker (U2-Net, local, optional)
            broll.py      finds stock (Pexels through the project's store) or local footage; records credits
            score.py      original music, sound design, mix to -14 LUFS
            stamp.py      the Cascade paint-stroke sign-off
       4. cinema/project.py            saves project.json + edited.mp4 as version v001, v002, ...
Follow-up in the same chat
  -> cinema/revise.py                  switches and simple timeline changes, no AI
  -> cinema/planner.py revise()        creative changes, starting from the saved plan (not from scratch)
```

## Where the editing intelligence is stored

| File | What it holds |
|---|---|
| `backend/editor/ai_edit/cinema/STYLE_GUIDE.md` | The creative direction and editing rules, in prose |
| `backend/editor/ai_edit/cinema/INSPO_NOTES.md` | Notes on all 28 INSPO references and the reference trailer |
| `backend/editor/ai_edit/cinema/prompts/director.md` | The planner's instructions (story planning, moments, b-roll, message) |
| `backend/editor/ai_edit/cinema/style.json` | The numbers: pauses, caption sizes, colours and their words, levels, pacing |
| `backend/editor/ai_edit/cinema/plan.py` | The plan format, validation, and the rule-based director |
| `backend/editor/ai_edit/cinema/*.py` | The craft itself, as code |
| `backend/editor/ai_edit/cinema/CLAUDE.md` | Ground rules for whoever (or whichever model) maintains this folder |

## Choosing the planner and the model

Set these in `.env` and restart the backend. Nothing else changes.

| Variable | Values | Meaning |
|---|---|---|
| `CASCADE_EDIT_PLANNER` | `auto` (default) | Claude Code CLI if signed in, else a custom command if set, else the rule-based director |
| | `claude` | Only the Claude Code CLI |
| | `command` | Only the program in `CASCADE_EDIT_PLANNER_CMD` |
| | `rules` | No AI at all |
| `CASCADE_EDIT_MODEL` | unset (default) | The Claude CLI's own default model for your subscription |
| | `opus`, `sonnet`, or a full model id | Passed to the CLI as `--model` |
| `CASCADE_EDIT_PLANNER_CMD` | a shell command | Reads `{"system", "prompt"}` JSON on stdin, prints a plan as JSON. Use it for a local model (Ollama) or any other tool |
| `CASCADE_EDITOR_CLAUDE` | `off` | Never call Claude (the tests use this) |
| `CASCADE_EDIT_ENGINE` | `cinema` (default), `legacy` | `legacy` brings back the older HyperFrames looks |

Examples: to pin planning to Opus, `CASCADE_EDIT_MODEL=opus`. To use whatever the subscription offers,
leave it unset. To add a different provider, write a function `(system, prompt, images) -> dict` in
`planner.py` and add it to `BACKENDS`.

The Claude planner runs through `claude -p` signed in with a Claude subscription. API keys are stripped
from its environment, so planning is never billed per request.

## What works with no AI model

- Playing and exporting any saved edit (`edited.mp4` is a file; `project.json` re-renders with `engine.make`).
- A first edit: the rule-based director (`plan.auto`) plans it. The chat says so.
- These follow-ups (`revise.py`): reel / original / square, music up / down / off / back, captions on / off,
  no or less b-roll, no sign-off, no opener, no cold open, no giant words, shorter,
  and a new title, opening word or closing message given in quotes.
- A creative follow-up ("open on a different line") with no planner available is refused with a clear
  message and the draft is left exactly as it was.

## A saved edit

`video_jobs/projects/<project>/editor/<editor>/ai-edits/<job>-<clip>/vNNN/`

- `project.json`: `plan` (story order, cuts, keywords, moments, b-roll, mood, message, settings),
  `planner` (who planned it), `request`, `source.credits` (where each stock shot came from),
  `timeline` (the resolved dialogue pieces, shots, overlays and music silence it rendered to), `report`
  (length, loudness, per-stage timings).
- `edited.mp4`: the render.
- `versions.json` one level up lists every version; each follow-up adds a version and never overwrites one.

To change an edit by hand, edit `plan` in `project.json` and render it:

```python
from backend.editor.ai_edit.cinema import engine, project, broll
plan = project.load('…/v002')
engine.make('source.mp4', words, plan, '…/v003/edited.mp4', find_broll=broll.resolver(None, ['my-footage-folder']))
```

## Tests

```
python -m pytest tests/application/test_cinema.py tests/application/test_ai_edit.py
```

They run with every AI planner switched off and cover: dialogue cleaning, the rule-based director,
planner fallback and the custom-command planner, AI-free revisions, project save and reopen, a real
render to Original and to 9:16 (needs FFmpeg), and the chat job flow end to end.

## Continuing development

Open the repo in Claude Code with any model and say what you want changed. `cinema/CLAUDE.md` loads
automatically when that folder is touched. Useful starting requests:

- "Read docs/cinema-editor.md and cinema/STYLE_GUIDE.md, then …"
- Taste changes: edit `prompts/director.md` or `style.json`, render a clip, look at a contact sheet.
- New looks: add an overlay kind in `render.py`, a `style` in `plan.Moment`, and a line in the prompt.
- New AI-free follow-ups: add a rule to `revise.py` and a test.

## Known limits

- The Editor shows an AI edit as a rendered version; its pieces are not yet draggable clips on the
  Editor's own timeline. The timeline is data in `project.json`.
- Telling two voices apart by sound is a safety net; the planner reading the transcript does most of it.
- The music is composed by code, not licensed tracks. Stock b-roll is Pexels (Pexels License, no
  attribution required; sources are recorded per project anyway). Fonts are SIL OFL (`cinema/fonts/LICENSES.md`).
- The first edit that uses a word behind the speaker downloads a 176 MB cut-out model once.
- No model can hear the clip. Planning uses the word-timed transcript and contact sheets.
