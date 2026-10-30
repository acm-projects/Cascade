# MLK integration — October 30, 2026

Work stays on `manila/scheduled-publishing`. No push or shared-branch merge.
The previously unfinished merge of `164bd0b` was completed as `8da8ad7`.
The subsequent merge includes `origin/MLK` at `1583322`, including `2e78352`.

## Recovery backup

Private persistent directory (outside Git):
`/Users/manila/Documents/Cascade2/Cascade-merge-backups/20261030-105009`.
A second copy remains in `/private/tmp/cascade-merge-backup-20261030-105009`.

`working-tree.tar.gz` includes existing tracked/nonignored working files, including
conflict markers. `git-state.tar.gz` contains the complete pre-resolution `.git`
directory: objects, refs, index stages, merge metadata, and reflogs. The directory
also contains staged/unstaged binary patches, index stages, status and a manifest.
Archives were opened to verify their contents; the persistent copies were checked
byte-for-byte against the originals. Directory permissions are 0700; files 0600.

`.env*`, `.local-https/`, and ignored generated media were deliberately left in
place and untouched; they are not included in the working-file archive. This is
a merge-state backup, not a backup of the user's media library or configuration.
Do not extract the Git archive over an active repository casually: restore both
archives to a separate recovery directory if the old merge state is needed.

## Resolution decisions

- Keep `app1.py` as the compatibility entry point to `backend.main`.
- Port remote upload/generation changes into `backend/routers/clips.py` and
  `generations.py`: 50-clip bounds, combined-reference context, prior-session
  exclusions, source reuse, and stable progressively available clip indexes.
- Keep obsolete `backend/integration.py` and `project_actions.py` deleted.
  Their ownership/selection and validation changes live in
  `backend/services/projects_store.py` and the generation router.
- Keep lifecycle and shared selection behavior in `backend/studio.py`; adapt
  the new session-exclusion service to the restructured modules.
- Combine accessible modal focus handling with the team's wide-modal option.
- Keep the team's caption presets/text tab, aspect controls, playback, chat
  change summaries and new-project dialog alongside advanced editing, caption
  animation, B-roll, Music, Reel, retiming and Trends.
- Use one serialized draft-save queue, flush before navigation/download, and
  retain autosave-on-unmount and unsaved-change protection.
- Keep the latest Exports layout, grouping independent sessions by stable IDs
  even when users give them the same name. Preserve Trends and saved-edit
  downloads; stack the existing panels on mobile instead of clipping them.
- Scheduling files are preserved without new routes/workers or completion claims.

## Run locally

Use the existing private configuration. Do not replace `.env`.
From the repository root, in one terminal:

```sh
.venv/bin/python -m uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, also from the repository root:

```sh
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173** for the integrated React interface. Vite proxies
`/api`, `/upload`, `/jobs` and `/clips` to port 8000. Port 8000 continues serving
the legacy interface and existing OAuth callbacks; this integration does not
change the team's deferred production frontend-serving migration.

Existing dependencies must be installed (`requirements.txt`,
`requirements-dev.txt`, `frontend/package-lock.json`); FFmpeg/FFprobe with libass
are required for captioned exports. Local tests installed the declared pytest
development dependency into `.venv`. No configuration values were printed or
changed. Clerk, AI/transcription, media storage and OAuth configuration continue
to use their existing setup. No new API credentials or redirects are introduced.

## Validation

```sh
PYTHON_DOTENV_DISABLED=1 CASCADE_METADATA_STORE=local CASCADE_STORAGE=local CASCADE_WARM_MODELS=0 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
PYTHON_DOTENV_DISABLED=1 CASCADE_METADATA_STORE=local CASCADE_STORAGE=local CASCADE_WARM_MODELS=0 .venv/bin/python -m pytest backend/tests -q
PYTHON_DOTENV_DISABLED=1 CASCADE_METADATA_STORE=local CASCADE_WARM_MODELS=0 .venv/bin/python -m unittest discover -s backend/tests -q
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
node tests/test_editor_state.cjs
node tests/test_editor_flow.cjs
node tests/test_canvas_branches.cjs
```

Results: 368 application checks completed successfully (24 explicit skips),
165 agent pytest tests passed, 11 agent unittest checks passed, 67 frontend tests
passed, three Node suites passed, and production build passed. Lint exits zero
with two pre-existing `set-state-in-effect` warnings in MusicControls/ClipPlayer.
The stale route-contract check now explicitly enumerates the six audio/Trends
additions; the existing 423-line Trends module has a bounded 450-line exception.
Other modules retain the original size budget. No legacy routes were removed.

The upload → generation → editor/chat → save/reload → export backend test uses
real local media/FFmpeg, isolated identity/storage and mocked paid selection.
Ownership and lifecycle tests are included. No live provider operation occurred.

Isolated Chrome also passed the advanced-editor test and
`tests/test_merged_react_browser.py`: Music previews/add/remove, shared audio
state, multi-edit chat, undo/redo, caption presets/animation, aspect controls,
Trends opening without edits, navigation/persistence, latest Exports layout,
real single/ZIP downloads with equal decoded frames, and mobile layout. Browser
artifacts are at `/private/tmp/cascade-merged-browser-zqj4cjs_`.

To reproduce the React browser test, build the frontend, run
`PYTHON_DOTENV_DISABLED=1 CASCADE_METADATA_STORE=local CASCADE_STORAGE=local CASCADE_FIXTURE_PORT=18771 .venv/bin/python tests/advanced_editor_browser_server.py`,
start isolated headless Chrome with DevTools on port 9333, then run
`CASCADE_BROWSER_TESTS=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH=.:tests .venv/bin/python tests/test_merged_react_browser.py`.
The fixture server uses temporary storage and mocked identity/providers; never
run it as the production application.

Live Clerk/OAuth, cloud storage, paid AI/transcription/research and external
publication remain outside this offline integration verification. Scheduling is
still incomplete and paused. Existing user servers were not stopped.
