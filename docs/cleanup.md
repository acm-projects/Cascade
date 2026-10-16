# Project cleanup audit

Checkpoint: `dd3b7c2` (Save editor updates and mutli-clip fixes before cleanup). The working tree was clean on `manila/editor-work` before cleanup. Cleanup is intentionally uncommitted.

## Organization

- Moved the seven active HTML pages and seven shared/editor assets into `web/`, without changing any of their contents or public URLs.
- Moved integration, editor backend, scene analysis, timing and FFmpeg helpers into `backend/`; updated static and lazy imports and test patch targets. Kept `app1.py` and the existing startup command.
- Grouped editor documentation and historical multi-clip findings under `docs/`. Replaced stale setup instructions with `docs/setup.md` and the root README; corrected research-package startup documentation.
- Moved four opt-in smoke scripts to `tests/manual/`. Kept regression tests and browser fixtures under `tests/`. Added a public URL/asset contract check and safe configuration template.

## Removed

- Superseded Flask `app.py`, standalone subtitle `main.py`, old root `preferences.py`, `templates/settings.html`, `index.html`, and simulation `app_C.js`.
- Old standalone `caption_video.py`, `select_clips.py`, and duplicate root `render_subtitles.py`. The current generation and caption workers remain in `app1.py` and `backend/`.
- Code-only prototypes in `sample/`: `cascade_clips.py`, `wed.py`, `wed1.py`, `front.html`. The unrelated root media file `sample.mp4` remains.
- Unmounted diagnostic static pages under backend static directories; unused clips/settings HTTP wrappers and the settings template. Active workers, renderers and preferences remain. The dead renderer entry point referencing a nonexistent sample was removed.
- One-off investigation replay scripts, duplicate/stale root documentation, and obsolete `test_neon.py`. The diagnostic contained a committed credential: removing its file does not revoke that credential or remove Git history; rotate it separately.
- Direct Flask, psycopg2-binary and Jinja2 requirements, whose only application consumers were removed legacy implementations. No other dependency pruning was attempted.
- Disposable Python bytecode caches in source/test directories. Saved provider caches are retained.

## Deliberately retained

`.env`, all saved jobs/projects/media/transcripts/editor drafts/exports, root `outputs/`, root JSON records, root `sample.mp4`, and provider caches were left untouched. A pre-cleanup SHA-256 manifest covers 588 existing data/configuration files and is checked after validation. Root `login.html` remains because authentication reads its publishable-key fallback; it is not exposed by the static whitelist. Unmounted router definitions inside active research/search worker modules remain to avoid unnecessary refactoring.

## Validation

- Production `uvicorn app1:app` started successfully. Root and all 14 public page/asset URLs returned HTTP 200. Route regression checks cover local HTML references and denial of configuration/source paths.
- 56 Python regression tests passed; two Node state/DOM suites passed. Provider operations are mocked. Active backend feature/dependency imports resolve, including search, research, preferences and caption rendering.
- Isolated real Chrome checks passed: local media playback, captions, trim/scrub, zoom/scroll, AI response synchronization, comparison, aspect presets, Fit/Fill/repositioning, undo/redo, independent clip drafts and reload. Identity and AI were fixtures; media decoding and exported MP4 encoding were real.
- Downloaded exports were probed and compared with preview composites. Caption/trim test: 6-second output, mean pixel error 3.04/255. Fit/Fill tests: 360×640, 1-second outputs, mean pixel errors 2.58/255 and 3.93/255 (lossy H.264).
- All 14 moved frontend files are byte-for-byte identical to the checkpoint, including canvas and generation-facing scripts. Backend generation changes are import-path updates only.

No paid AI, live Clerk sign-in, live YouTube/Anthropic research, S3 delivery or fresh provider-backed generation was invoked. Cross-browser/device coverage and installation into a fresh environment were not verified. Existing installed dependencies were used. Test artifacts/logs are in `/tmp/`, outside saved project storage.
