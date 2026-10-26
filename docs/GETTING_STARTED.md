# Getting started

For backend installation, `.env` keys and storage, see [Setup and runtime](setup.md).

## Running both servers

Local development uses two servers:

| Server | What it serves | URL |
|---|---|---|
| FastAPI (`app1.py`) | APIs, uploads, jobs, clips | http://127.0.0.1:8000 |
| Vite (`frontend/`) | The React app | http://localhost:5173 |

Start each one in its own terminal, from the repository root.

Terminal 1, the backend:

```sh
source .venv/bin/activate
python -m uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2, the React app:

```sh
cd frontend
npm install   # first time only
npm run dev
```

Open http://localhost:5173.

### How React reaches the backend

`frontend/vite.config.js` proxies `/api`, `/upload`, `/jobs` and `/clips` to the backend on port 8000. React code uses relative URLs only:

```js
fetch("/api/health") // → {status: "ok"}
```

Never hard-code `http://127.0.0.1:8000` in `frontend/src`. The browser treats port 5173 and port 8000 as different origins (CORS), and in production FastAPI serves the built React files itself, so relative URLs keep working there too.

### Troubleshooting

- **`/api/...` returns the React page's HTML.** Vite isn't proxying. Restart `npm run dev` after any change to `vite.config.js`, and make sure it was started from `frontend/`.
- **`403 Origin not allowed`.** The page's origin is missing from the allowed list. The default list in `authorized_parties()` (`app1.py`) includes ports 8000 and 5173. If your `.env` sets `CLERK_AUTHORIZED_PARTIES`, it replaces that default, so add `http://localhost:5173,http://127.0.0.1:5173` there. If Vite started on another port (for example 5174, because 5173 was busy), stop the other server or use that port's origin.
- **`401 Please sign in first`.** The proxy works and the backend wants a signed-in user. Sign in, or use the dev login once it exists (CAS-8).
- **`502` or `ECONNREFUSED` in the Vite terminal.** The backend isn't running on port 8000.
