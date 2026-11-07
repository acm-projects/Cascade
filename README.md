# Cascade

**New here? Start with [Getting started](docs/GETTING_STARTED.md)** — install, `.env`, running both servers, and troubleshooting.

[![CI](https://github.com/acm-projects/Cascade/actions/workflows/ci.yml/badge.svg)](https://github.com/acm-projects/Cascade/actions/workflows/ci.yml)

Cascade turns video and audio into searchable clips, with AI Studio, research,
caption styling, editing, exports, and publishing. It is a modular monolith:
React in `frontend/`, backed by one FastAPI application in `backend/`.

## Run locally

Install Python dependencies with `python -m pip install -r requirements.txt` and
install FFmpeg/FFprobe separately. If no `.env` exists, copy `.env.example`;
keep an existing configuration. Install React dependencies with
`npm --prefix frontend ci`.

From the repository root, start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173**. Port 8000 serves the API and retained legacy UI.
`uvicorn app1:app` remains a supported compatibility command. Generation and
research use configured external services and can incur charges; offline tests
mock those providers.

## Repository map

```text
frontend/
  src/                   Current React pages, features, API client, and styles
  public/                Public React assets
  legacy/                Retained older website and its Studio bundle source
backend/
  main.py                FastAPI application and router registration
  core/                  Authentication, configuration, jobs, and storage
  routers/               HTTP routes
  services/              Project, session, and feature services
  database/              Metadata store, migration CLI, and SQL migrations
  agent/                 Clip selection, indexing, and research integration
  editor/                Editor models, actions, rendering, and research
  ...                    Media, providers, search, tracking, and publishing
tests/
  application/           Offline application/API regressions
  agent/                 Agent/provider/transcription/selection tests
  browser/               Opt-in browser checks and fixture servers
  javascript/            Legacy JavaScript regression checks
  fixtures/              Route contract snapshot
  manual/                Opt-in media/provider/database checks
scripts/                 Setup, evaluation, and diagnostic commands
docs/                    Guides, architecture, database diagrams, and evidence
```

Root requirements files are installation entry points; `app1.py` is a tiny
compatibility entry point. `.github/` holds CI. Runtime data is private, not
disposable source: keep `.env`, `video_jobs/`, input media, and model caches.

See the [detailed map](docs/codebase-layout.md), [tests](tests/README.md),
[setup](docs/setup.md), [database](docs/database/README.md),
[CI](docs/ci.md), and [cleanup record](docs/codebase-organization.md).
Feature guides cover [editing](docs/editor.md), [B-roll](docs/broll.md),
[Auto Reframe](docs/auto-reframe.md), and [generation performance](docs/generation-performance.md).
