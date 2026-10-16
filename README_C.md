# Cascade integrated website

The updated website runs through the existing Clerk-authenticated FastAPI app on `cascade/integration`.

See [INTEGRATION.md](INTEGRATION.md) for dependency installation, services/configuration, exact startup commands, verification, and remaining unfinished controls.

AI scene analysis now uses OpenAI by default to select up to four distinct clips
from sampled images and timestamped transcript text. Add `OPENAI_API_KEY` to your
existing local `.env`; the default model is `gpt-5.4-mini` (override with
`OPENAI_SCENE_MODEL`). Ollama can stay off. Transcription and FFmpeg rendering
remain local. Local visual/speech search and the legacy Ollama mode are optional
alternatives. The timing panel shows each stage; fewer than four supported
matches are explained instead of duplicating clips.

Local visual and speech search also return up to four non-overlapping clips.
They rank image/transcript matches once per job, preserve audio, and generate
separate captions for each result. When necessary to fit four distinct moments,
they can shorten the preferred duration down to eight seconds and explain the
change. They return fewer if four separate searchable moments cannot fit.

Windows startup from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

After installing dependencies and starting the required services, run from the repository root:

```bash
source .venv/bin/activate
python -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/. HTML files should not be opened directly or served with the simple Python static server: authentication and media require the backend.

Active pages are `index_C.html`, `login_C.html`, `projects_C.html`, `canvas_C.html`, `editor_C.html`, and `exports_C.html`, and `settings_C.html`, with `flow_C.js` and `styles_C.css`. The separate `app_C.js` simulation prototype is preserved but unused by these pages.
