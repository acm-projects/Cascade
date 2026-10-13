# Cascade integrated website

The updated website runs through the existing Clerk-authenticated FastAPI app on `cascade/integration`.

See [INTEGRATION.md](INTEGRATION.md) for dependency installation, services/configuration, exact startup commands, verification, and remaining unfinished controls.

After installing dependencies and starting the required services, run from the repository root:

```bash
source .venv/bin/activate
python -m uvicorn app1:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/. HTML files should not be opened directly or served with the simple Python static server: authentication and media require the backend.

Active pages are `index_C.html`, `login_C.html`, `projects_C.html`, `canvas_C.html`, `editor_C.html`, and `exports_C.html`, with `flow_C.js` and `styles_C.css`. The separate `app_C.js` simulation prototype is preserved but unused by these pages.
