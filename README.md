# Cascade

Cascade turns uploaded videos into searchable clips and provides project management, research, caption styling, and a nondestructive video editor. The current website uses FastAPI and Clerk authentication.

Start from the repository root:

```sh
python3 -m pip install -r requirements.txt
cp .env.example .env  # Only when creating a new configuration; keep an existing .env.
uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

Install FFmpeg/FFprobe separately. See [setup and configuration](docs/setup.md), [editor behavior and browser checks](docs/editor.md), and [multi-clip investigation](docs/multi-clip-investigation.md).

```text
app1.py                  FastAPI entry point, authentication, upload/generation
backend/                 Project/editor services and feature implementations
web/                     Active pages, scripts, and styles (stable public URLs)
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
```

Some media tests require FFmpeg with the `subtitles` filter (libass). On Homebrew, install `ffmpeg-full` and put its `bin` directory first in PATH. Tests mock paid providers; scripts under `tests/manual/` are opt-in and may use configured external services. Do not run them as part of an offline test suite.

Keep `.env`, `video_jobs/`, `outputs/`, and other saved media private. They are not disposable build output. Root `login.html` remains a legacy authentication configuration fallback, not a served page. Root JSON records and `sample.mp4` are retained because their ownership/provenance is uncertain.
