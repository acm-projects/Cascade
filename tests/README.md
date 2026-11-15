# Tests

Run from the repository root using the project environment. Install
`requirements.txt` and `requirements-dev.txt`; media checks need FFmpeg/FFprobe
with subtitle/libass support.

## Offline checks

Disable personal dotenv configuration and use local fixture storage:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:CASCADE_METADATA_STORE = 'local'
$env:CASCADE_STORAGE = 'local'
$env:CASCADE_WARM_MODELS = '0'
$env:CASCADE_BROWSER_TESTS = '0'
python -m unittest discover -s tests -t . -p 'test_*.py' -q
python -m unittest discover -s tests/agent -q
python -m pytest tests/agent -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
node --test tests/javascript/*.cjs
```

`application/` holds API/render regressions; `agent/` contains pytest and unittest
suites. React tests remain colocated with React source. `fixtures/` preserves
the explicit route contract. `javascript/` tests retained legacy behavior.
The React test discovery also finds the retained Studio graph test.

## Browser checks

`browser/` contains procedural DevTools suites and isolated fixture servers.
They skip default discovery through `tests/browser_support.py`. Start the
matching fixture server and isolated Chrome described in the suite docstring,
then set `CASCADE_BROWSER_TESTS=1`. Prefer module execution, for example
`python -m tests.browser.editor_browser_server` and
`python -m tests.browser.test_editor_browser`.

## Manual checks

`manual/` contains explicit source-media, render, provider, and database checks;
read each script before running it. Live checks can contact external services,
incur charges, or modify a test database, and are excluded from offline CI.
`scripts/check_database.py` is a separate read-only Neon diagnostic.
