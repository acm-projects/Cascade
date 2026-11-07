# Codebase map

Cascade is one FastAPI application plus the current React client. Start it with
`python -m uvicorn backend.main:app`; `app1.py` delegates to the same app object.

## Frontend

`frontend/src/pages/` contains routed screens. `features/` groups Studio, editor,
and export behavior; `api/` owns HTTP calls. `components/`, `styles/`, and `utils/`
hold shared UI, theme, and utilities. React tests stay beside their source.
`public/` and `src/assets/` contain served and bundled assets.

`frontend/legacy/web/` is the older website still served by FastAPI.
`frontend/legacy/studio-ui/` builds that website's React Flow bundle. These remain
for compatibility; see [the legacy boundary](../frontend/legacy/README.md).

## Backend

`main.py` composes routes and startup hooks. `core/` owns configuration, auth,
jobs, and storage. `routers/` handles HTTP; `services/` handles project/session
operations. `database/` owns Neon/local metadata persistence, migration commands,
and SQL. Its `legacy_schema.sql` documents the earlier public schema; active
additive migrations live in `database/migrations/`.

`agent/` owns indexing, selection, intent, and agent tools. `cascade_llm/` and
`cascade_stt/` wrap providers. `editor/` owns editor state, validation, execution,
rendering, and research coordination. `trends/` and `video_search/` keep their
pipelines. `clips/render_subtitles.py` implements caption-style generation;
`settings/preferences.py` supplies defaults still used by the current service.

Shared backend modules cover media, FFmpeg, B-roll, social publishing, scheduling,
tracking, and reframing. Public import facades such as `editor_backend.py` remain
for callers while their implementation lives in feature packages.

## Supporting files

`tests/README.md` describes test groups. `scripts/` holds explicit developer
commands. `docs/architecture/` holds integration maps; `docs/database/` holds
database guidance and diagrams; `docs/deployment/` and `docs/verification/` hold
evidence. Older investigation documents remain historical records.

Root requirements files preserve existing install commands. Runtime packages are
listed in `backend/requirements.txt` plus root integration dependencies.
`.env`, virtual environments, `video_jobs/`, local input media, and model caches
are local runtime files. VS Code hides disposable logs, bytecode, dependencies,
and tooling caches without deleting them; saved jobs and configuration stay
visible. Never commit credentials or private media.
