# Fan-edit effects (AI Editor chat)

Free, local "fan edit" styling: subject cutouts with swapped backgrounds, color pop, shape
reveals, outlines/glow, ink, glitch, zoom/whip blur, flashes and an "Edited by" end card,
synced to beats (music track, else the clip's own audio, else 120 BPM) and scene cuts.

## Cost and privacy

Everything runs on this machine. Subject mattes use Meta's SAM 2.1 tiny through the installed
`transformers` package, prompted by the existing YOLOX detector (`scripts/setup_reframe.py`).
The only network use is the one-time download of the public `facebook/sam2.1-hiera-tiny`
weights from Hugging Face. Style requests are parsed deterministically, so they use no
Gemini quota. When the free Gemini daily quota runs out, other chat edits fall back to the
local Ollama model instead of failing.

## Chat examples

- `make this a spiderman fan edit, edited by Manila`
- `make the background gray and keep him in color`
- `comic background please` / `neon outline glow` / `subtle fan edit with paper backgrounds`
- `add a glitch from 2 to 3 seconds`
- `remove the fan edit`

## How it works

- `backend/editor/stylize.py`: request parsing, beat-synced preset planning, the render
  stage and its cache (`video_jobs/<job>/stylize/`).
- `backend/editor/style_effects.py`: procedural backgrounds and per-frame effects.
- `backend/editor/segmentation.py`: cached subject mattes, 6 samples per second,
  interpolated in time.
- The edit stores `stylize` events in generated-clip seconds. Export and preview bake them
  into a same-size, same-duration copy of the clip before the normal pipeline, so trim,
  captions, B-roll and OpenChatCut sequences all still apply.

The first preview of a new style computes cutouts (about 0.3 s per sampled frame on an M4
Pro); later previews reuse the cache. Tests: `tests/application/test_stylize.py`.

## AI Director (open-ended requests)

Requests like `edit this video`, `make this viral`, `make a memorial edit` or `you decide` go to the
AI Director (`backend/editor/director.py`) instead of always making a fan edit:

1. **Watch**: the free Gemini tier watches a 360p proxy of the clip with audio and transcript
   (genre, era, mood, key moments, important words, B-roll ideas). Falls back to the local Ollama
   vision model, then to transcript keywords.
2. **Inspire**: `inspiration.py` searches public YouTube with yt-dlp (no API key) for that kind of
   edit, downloads the two shortest popular references at low resolution, measures cuts per
   minute and shows the planner their frames. Cached for a week.
3. **Plan and apply**: the planner picks a style (memorial, podcast, fan edit, hype, cinematic,
   clean); `director_recipes.py` applies it with existing features: film look or grade, music
   from the built-in library, push-ins or punch-ins on key moments, a few important words,
   B-roll from the project's own source video (`source_broll.py`, using the cached search index)
   or free Pexels stock, pause tightening for podcasts, fades, and "Edited by Cascade".

Each Director edit uses two free Gemini requests; when the daily free quota is used up it keeps
working with local models. The paid research agent (Anthropic/OpenAI) is never called.
