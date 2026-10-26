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

## App users and Clerk

All active app storage is in **cascade_app**. `migrations/002_clerk_users.sql`
creates **cascade_app.users** with just `clerk_user_id` (primary key) and
`created_at` (first app registration time, not Clerk signup time). The migration
preserves existing Clerk-linked registration dates from the earlier public.users
integration. Sample users without Clerk IDs are not imported. Old public tables
are retained as legacy data; the running app never reads or writes them.

The verified `/api/session` request registers a user idempotently after sign-in
or signup. Project/job writes ensure their owner exists in the same transaction.
A foreign key on `cascade_app.records.owner_clerk_user_id` points to
`cascade_app.users`, keeping users and their projects/jobs in the same schema.
Passwords, emails, usernames and sessions remain managed by Clerk. No extra
profile fields or authentication tables are introduced. Deleting a Clerk account
does not yet delete app data.

Check user entries in Neon SQL Editor (or select the cascade_app schema in Tables):

```sql
SELECT clerk_user_id, created_at FROM cascade_app.users;
```

The existing Clerk forms still control which signup/login fields are required.
To require email/password or enable username, set those fields consistently in the
Clerk dashboard; no independent password form or duplicate login table is added.

## AI Studio sessions

The branching React Flow studio stores its named sessions, conversation history,
node positions, viewport, reference clips and Editor choices inside each existing
project's `studio` JSONB field under `cascade_app.records`. Job ownership records
include the session ID and all parent clip references. This introduces no new
tables. See [docs/studio.md](docs/studio.md) for the UI, API and build workflow.

Video/audio files, thumbnails, transcripts and model caches are **not** stored in
Postgres. Original uploads and working files remain in `video_jobs`. Generated
clips/captions use S3 when configured, or local storage otherwise. Keep this
directory to reopen original videos or rerender clips. Moving metadata to Neon
does not turn the local FFmpeg worker into a distributed queue or upload sources
to S3. Continue using one Uvicorn worker.

## Existing installation

### Projects page

`003_project_page.sql` extends the existing project JSONB records and the
`cascade_app.projects` view, without adding tables. Projects contain `id`,
`user_id`, `name`, `created_at`, `updated_at`, `thumbnail_key` (nullable), and
existing saved clip references. Existing projects are backfilled without changing
their names, ownership, creation dates or saved clips. Thumbnail references are
reserved for future generated previews; this change does not generate images.

`GET /api/projects?q=...` searches the authenticated user's project names and
sorts by edit time. `PATCH /api/projects/{id}` renames an owned project atomically
without replacing saved clips. Creating a job, completing results, saving a clip,
and renaming update edit time. Merely viewing or searching does not. Search text
is not persisted. Recent/Favorites/Archives/Trash remain placeholders and have no
database flags or tables yet.

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
