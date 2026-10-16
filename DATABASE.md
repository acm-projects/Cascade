# Neon persistence

The active FastAPI app uses the secret `DATABASE_URL` in the root `.env`.
With `CASCADE_METADATA_STORE=auto` (the default), a configured URL selects Neon;
without one, development uses local JSON. Set `CASCADE_METADATA_STORE=neon` to
require Neon. An unavailable configured database returns HTTP 503; it never
silently reports a successful local-only save. Keep the URL out of Git and the browser.

## Data layout

`migrations/001_metadata.sql` adds the `cascade_app` schema without changing the
existing `public` tables. `cascade_app.records` stores the app's validated JSON
documents in PostgreSQL JSONB. SQL views expose them as:

- `cascade_app.projects`: project IDs/names, Clerk user IDs, saved clip references.
- `cascade_app.settings`: account preferences, keyed by the hash of the Clerk ID.
- `cascade_app.jobs`: owners, project links, prompts, status/timings, results and errors.
- `cascade_app.clips`: generated clip metadata and local/S3 media references.

This preserves the current API contract and older project IDs. Clerk remains the
identity provider; the app does not copy passwords into Neon. Database access is
server-side only. Authenticated endpoints still enforce project/job ownership;
this is not a browser-facing database role or an RLS-based public API.

Video/audio files, thumbnails, transcripts and model caches are **not** stored in
Postgres. Original uploads and working files remain in `video_jobs`. Generated
clips/captions use S3 when configured, or local storage otherwise. Keep this
directory to reopen original videos or rerender clips. Moving metadata to Neon
does not turn the local FFmpeg worker into a distributed queue or upload sources
to S3. Continue using one Uvicorn worker.

## Existing installation

Stop the API before migrating, then run from the repository root:

```powershell
.\.venv\Scripts\python.exe migrate_metadata.py
.\.venv\Scripts\python.exe -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

The import copies existing projects, per-user settings and durable job records.
It is repeatable: existing database keys are never overwritten, and local files
are retained. Startup also applies the additive schema. After import, reads use
Neon as the source of truth; JSON files are retained as working copies, not a
database outage fallback. Back up Neon as well as local media. To import another
machine's old records, stop its API and run the same import against its job folder.

`GET /api/health` checks the database and reports `metadata_storage: "neon"`.
Completed jobs survive API restarts. Interrupted processing still requires a retry.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
# Explicitly opt into disposable writes against the configured Neon database:
.\.venv\Scripts\python.exe tests/live_neon_smoke.py --allow-database-writes
```

Unit tests select local metadata and mock external providers. The optional live
test verifies project/settings/history/clip persistence without local JSON and
checks isolation between users. It removes only its synthetic records afterward;
it makes no AI, Clerk, S3, or model requests.
