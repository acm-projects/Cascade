# One HTML source, existing page URLs

`web/index.html` is the only HTML source file. It contains conditional views for Home, Login, Projects, Canvas, Editor, Exports and Settings. `backend/frontend.py` renders exactly one view through the existing FastAPI frontend routes. CSS, JavaScript, backend services and assets remain separate. The startup command remains `uvicorn app1:app`.

The public URLs `/`, `/index_C.html`, `/login`, `/login_C.html`, `/projects_C.html`, `/canvas_C.html`, `/editor_C.html`, `/exports_C.html`, `/settings_C.html` and `/settings` retain their behavior. `/index.html` is an additional home alias. Query parameters identifying projects, jobs and clips are preserved. Navigation still uses ordinary document links, so direct links, refresh and native Back/Forward use the existing browser routing rather than a new client router.

Each response contains only its selected page's head/body/styles/scripts. It does not mount seven hidden pages: duplicate IDs, cross-page style leakage, duplicate listeners and background media are avoided. Original markup, inline styles and asset ordering were copied intact. Jinja uses HTML-comment block delimiters so CSS/JS braces are literal. A whitelist selects views; raw template source is never served. Jinja2 is an explicit backend requirement.

The superseded seven `*_C.html` source files and old root `login.html` were removed after verifying all rendered views matched their original documents byte-for-byte. The legacy HTML was not an active website page; its publishable-key fallback was migrated to a private template declaration, preserving the existing environment-first Clerk configuration. No secret environment file was copied into the template or changed. The publishable key is public configuration; secret keys remain server-only.

On leaving a view, its audio/video is paused. Non-cached documents release their protected media URLs. Browser Back/Forward cache preserves its existing DOM/listeners and valid media URLs rather than remounting it; restored canvases refresh saved groups without triggering generation.

## Canvas branches

Generations remain distinct columns in one horizontal strip: children, siblings and new full-video requests never wrap below earlier columns. Source clip IDs, prompts, counts and generation order use the existing persisted job records. Connections use curved colored paths based on the selected parent clip, with separate overhead lanes for connections that span intermediate columns. Existing parent labels/reveal actions, horizontal wheel/touch/scrollbar navigation, new-column auto-scroll and prompt history/reuse/retry remain available. Generation, captions, editing and export logic were not replaced.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -q
node tests/test_editor_state.cjs
node tests/test_editor_flow.cjs
node tests/test_canvas_branches.cjs
# With isolated Chrome on port 9333, start this fixture server:
python3 tests/project_browser_server.py
# In a separate terminal (each destructive fixture scenario needs fresh server data):
python3 tests/test_frontend_browser.py
python3 tests/test_horizontal_browser.py
python3 tests/test_project_browser.py
```

`test_frontend_views.py` checks one HTML file, one head/body per view, unique DOM IDs, correct scripts, legacy aliases, source privacy and the preserved authentication fallback. During migration all seven rendered documents were verified byte-for-byte against pre-change originals saved outside the repository.

`test_frontend_browser.py` compares original and migrated fixture screenshots when the optional migration snapshots in `/tmp` are available. With fresh checkouts that do not have those snapshots, visual comparison is explicitly skipped; route/navigation/media/persistence/download checks still run. Screenshots are written under `/tmp/cascade-frontend-artifacts`. The identity and external Clerk widget are mocked consistently for before/after comparisons, not claimed to be live sign-in verification.

It also uses the real legacy URLs and native links, tests Back/Forward, paused media on leaving a view, caption/settings persistence, a real MP4 download, refresh and absence of generation requests caused by navigation. Existing editor browser checks use `tests/editor_browser_server.py` separately for actual caption/composition/export pixel comparisons.

Tests use temporary user/project storage and mocked identity/selection. Live Clerk sign-in/sign-up, cloud storage, paid providers, physical touch devices and cross-browser behavior require separate verification. No paid requests are made by these checks.

The migration run passed 69 Python tests and all three Node suites. All seven fixture screens were compared; the final screenshot mean differences ranged from 0 to 0.014/255 after waiting for autosave and clip thumbnails to settle. Original rendered HTML was byte-identical for every view. Real Chrome editor checks also downloaded and compared encoded caption/composition exports with their live previews. The normal production startup served all 19 checked public page/asset/alias URLs successfully.
