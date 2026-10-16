# Cascade integrated website

The updated website runs through the existing Clerk-authenticated FastAPI app on `cascade/integration`.

See [INTEGRATION.md](INTEGRATION.md) for dependency installation, services/configuration, exact startup commands, verification, and remaining unfinished controls.

The **AI agent** is the default way to find clips. It transcribes the video with Deepgram, then searches,
reads and compares moments across the whole video and returns up to four ranked clips spread through it. Set
`DEEPGRAM_API_KEY` and `LLM_PROVIDER` (`anthropic` by default, or `openai`) with the matching API key in your
`.env`; the models are fixed in code. A "What the agent is doing" panel shows each step while it works, and
there is no default time limit. Local visual/speech search are optional alternatives and transcribe with
Deepgram too (there is no local Whisper). The OpenAI scene-analysis and Ollama engines were removed.

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
