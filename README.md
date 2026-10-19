# Cascade

Cascade turns uploaded videos into searchable clips and provides project management, research, caption styling, and a nondestructive video editor. The current website uses FastAPI and Clerk authentication. Generation uses the existing clip agent, Deepgram transcription, configurable AI provider, and parallel video rendering. Editor chat independently uses OpenAI.

Start from the repository root:

```sh
python3 -m pip install -r requirements.txt
cp .env.example .env  # Only when creating a new configuration; keep an existing .env.
uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

Install FFmpeg/FFprobe separately. See [setup and configuration](docs/setup.md), [editor behavior and browser checks](docs/editor.md), and [multi-clip investigation](docs/multi-clip-investigation.md), and [project groups and follow-ups](docs/project-generations.md).

```text
app1.py                  FastAPI entry point, authentication, upload/generation
backend/                 Project/editor services and feature implementations
web/                     One HTML template (index.html), scripts, and styles
tests/                   Regression and isolated browser checks
  manual/                Explicit opt-in model/render smoke checks
docs/                    Setup, editor, investigation, and cleanup notes
video_jobs/              Private uploads, jobs, projects, drafts, and exports
```

Run offline regression checks from the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -q
node tests/test_editor_state.cjs
node tests/test_editor_flow.cjs
node tests/test_canvas_branches.cjs
```

Some media tests require FFmpeg with the `subtitles` filter (libass). On Homebrew, install `ffmpeg-full` and put its `bin` directory first in PATH. Tests mock paid providers; scripts under `tests/manual/` are opt-in and may use configured external services. Do not run them as part of an offline test suite.

Keep `.env`, `video_jobs/`, `outputs/`, and other saved media private. They are not disposable build output. All seven page views live in `web/index.html`; existing page URLs remain valid. The legacy publishable-key fallback was migrated there without changing authentication. See [frontend routing and verification](docs/frontend.md). Root JSON records and `sample.mp4` are retained because their ownership/provenance is uncertain.

Main’s separate Flask/database service and legacy backend modules remain available; their historical setup is retained in `README_C.md` and `INTEGRATION.md`. The website itself serves the consolidated views under `web/`. Pexels B-roll is available in the editor; see [B-roll setup and workflow](docs/broll.md).
