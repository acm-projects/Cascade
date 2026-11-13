# Codebase organization

This cleanup on `codebase-cleanup` reorganizes source without changing public
URLs, provider choices, or saved user data.

## Moves

- `web/` and `studio-ui/` → `frontend/legacy/`; template paths and tests updated.
- Metadata store, migration CLI, SQL migrations, and historical public schema →
  `backend/database/`. Run `python -m backend.database.migrate` from the root;
  it still reads root `.env` and `video_jobs/`. No migrations were executed.
- Root integration/database maps, diagrams, deployment evidence → categorized
  `docs/` folders. Existing visualization contents are preserved.
- Agent tests → `tests/agent/`; application tests → `tests/application/`;
  browser checks/servers → `tests/browser/`; JavaScript → `tests/javascript/`;
  route contract → `tests/fixtures/`.
- Database diagnostic → `scripts/check_database.py`; provider diagnostic →
  `scripts/check_openai.py`; live database smoke check → `tests/manual/`.

## Approved non-test deletions

The user explicitly approved these six files after reviewing the reasons:

- `projects_C.html`: unserved duplicate; its URL renders the consolidated template.
- `README_C.md`: outdated branch/setup and four-clip claims; current README and
  detailed guides replace it.
- `backend/settings/router.py` and `backend/settings/templates/settings.html`:
  unmounted standalone form; mounted settings routes and preference loader stay.
- `backend/clips/router.py`: unmounted prototype API; mounted clip routes and
  caption renderer stay.
- `backend/clips/sample.mp4`: unreferenced sample, unused by app or tests.

Recovery copies, original hashes, a move manifest, and a Git bundle are saved
locally in `.test-tmp/codebase-organization-backup/` (ignored). Git history also
retains tracked originals. No other non-test source is discarded.

## Test cleanup

Removed `tests/render_smoke.py` and `tests/live_search_smoke.py` only after
verifying exact duplicates of their `tests/manual/` copies apart from paths.
The canonical render smoke now mocks the existing transcription adapter rather
than removed Whisper code, keeping it offline.

Regression suites remain. Fixture classes are imported through modules to avoid
accidental duplicate unittest collection. Two pre-existing Windows failures in
debug-video copies use `tempfile.gettempdir()` instead of Unix-only `/tmp`.
Browser checks stay opt-in. No paid provider or database migration is invoked.

## Validation

- Application suite: 292 collected, 268 passed, 24 opt-in browser suites skipped.
- Agent checks: 165 pytest tests passed; 11 unittest tests also passed.
- Frontend: 70 tests passed, production build passed, lint completed with the
  same two pre-existing React effect warnings as the baseline.
- All six standalone JavaScript suites passed.
- Manual offline renderer: four real synthetic captioned MP4s with audio and
  matching VTT passed; transcription was mocked.
- File audit: no unapproved missing files; all local documentation links resolve.

Baseline application tests had two Windows-only `/tmp` debug-copy errors; those
were repaired. The reduced application count reflects removal of accidentally
recollected imported fixture classes, not discarded unique tests. Live browser,
provider, database, OAuth, and publishing checks were not run.
