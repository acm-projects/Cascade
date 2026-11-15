# Getting started

Run Cascade on your laptop: the FastAPI backend and the React app. First-time setup takes about 20 minutes, most of it `pip install`. For deeper configuration (storage, S3, Neon), see [Setup and runtime](setup.md).

## 1. Install the tools

| Tool | Version | Mac | Windows | Linux |
|---|---|---|---|---|
| Python | 3.11 or newer | `brew install python@3.12` | python.org installer | `sudo apt install python3 python3-venv` |
| Node.js | 20 or newer | `brew install node` | nodejs.org installer | nodejs.org or `nvm` |
| FFmpeg | any recent build | `brew install ffmpeg` (or `ffmpeg-full` for caption burn-in) | `winget install Gyan.FFmpeg` | `sudo apt install ffmpeg` |

Check them:

```sh
python3 --version
node --version
ffmpeg -version
```

## 2. Get the code and the Python packages

```sh
git clone https://github.com/acm-projects/Cascade.git
cd Cascade
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

This downloads PyTorch for the search models. It's big, so let it finish.

## 3. Create your `.env`

```sh
cp .env.example .env
```

Only do this once. If you already have a `.env`, keep it. Fill it in using the [table below](#env-variables). Ask whoever owns each account for the shared dev keys **privately**. Never paste keys into Linear, GitHub or Discord channels, and never commit `.env` (git already ignores it).

To run without Clerk keys, add `CASCADE_DEV_AUTH=1` (local only, see [Troubleshooting](#troubleshooting)).

## 4. (Optional) Face-tracking models

The Editor's 9:16 **Fill** framing follows the speaker using small local models. Download them once:

```sh
.venv/bin/python scripts/setup_reframe.py
```

Without them, Fill mode shows "Face model is missing". Everything else still works. Details: [Auto Reframe](auto-reframe.md).

## 5. Run both servers

Local development uses two servers:

| Server | What it serves | URL |
|---|---|---|
| FastAPI (`app1.py`) | APIs, uploads, jobs, clips (and the old site) | http://127.0.0.1:8000 |
| Vite (`frontend/`) | The React app | http://localhost:5173 |

Start each one in **its own terminal tab**, from the repository root, and leave both running.

Terminal 1, the backend (takes about a minute to start; wait for `Application startup complete` and `Search models loaded`):

```sh
.venv/bin/uvicorn app1:app --host 127.0.0.1 --port 8000
```

Add `--reload` if you're editing backend code and want it to restart on save.

Terminal 2, the React app:

```sh
cd frontend
npm install   # first time, and after pulling changes to package.json
npm run dev
```

Open http://localhost:5173. To stop a server, press `Ctrl+C` in its tab.

**Check it works:** http://127.0.0.1:8000/api/health should show `{"status":"ok", ...}`.

### How React reaches the backend

`frontend/vite.config.js` proxies `/api`, `/upload`, `/jobs` and `/clips` to the backend on port 8000. React code uses relative URLs only:

```js
fetch("/api/health") // → {status: "ok"}
```

Never hard-code `http://127.0.0.1:8000` in `frontend/src`. The browser treats port 5173 and port 8000 as different origins (CORS), and in production FastAPI serves the built React files itself, so relative URLs keep working there too.

### Test without real keys (fixture servers)

Two servers with fake data let you click through the app without Clerk, Deepgram or AI keys. Run each in its own tab, from the repository root:

```sh
.venv/bin/python tests/project_browser_server.py                       # fake backend on port 8767
frontend/node_modules/.bin/vite --config frontend/vite.fixture.config.js   # React app on port 5174
```

Open http://localhost:5174.

## 6. Run the checks

These are the same checks CI runs on every PR ([CI checks](ci.md)):

```sh
python -m unittest discover -s tests -p 'test_*.py' -q
python -m pytest backend/tests -q
cd frontend && npm run lint && npm test && npm run build
```

## `.env` variables

| Variable | Required? | What it's for | Where to get it |
|---|---|---|---|
| `LLM_PROVIDER` | Yes | Which AI runs the clip agent, summaries and Trends: `anthropic` or `openai` | Pick one |
| `ANTHROPIC_API_KEY` | If provider is `anthropic` | Clip finding, summaries, Trends, Editor chat | console.anthropic.com → API keys (team key) |
| `OPENAI_API_KEY` | If provider is `openai` | Same as above, with OpenAI | platform.openai.com → API keys (team key) |
| `DEEPGRAM_API_KEY` | Yes | Speech-to-text: clips, search, captions, Trends | deepgram.com dashboard (team key) |
| `CLERK_PUBLISHABLE_KEY` | Yes, unless `CASCADE_DEV_AUTH=1` | Sign-in (public key) | dashboard.clerk.com → API Keys |
| `CLERK_SECRET_KEY` | Yes, unless `CASCADE_DEV_AUTH=1` | Sign-in (server key) | dashboard.clerk.com → API Keys |
| `CLERK_AUTHORIZED_PARTIES` | Yes | Which page addresses may call the API (must include ports 8000 and 5173) | Keep the value from `.env.example` |
| `DATABASE_URL` | If `CASCADE_METADATA_STORE` is `auto`/`neon` | Neon Postgres for projects, users and jobs | Team Neon project |
| `CASCADE_METADATA_STORE` | No (default `auto`) | `local` keeps metadata on disk for offline development | Set `local` if you have no `DATABASE_URL` |
| `CASCADE_STORAGE` | No (default `auto`) | Where clips are stored: `local`, `s3`, `auto` | Use `local` for development |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `S3_BUCKET_NAME` | Only for S3 storage | Clip storage in S3 | Team AWS account |
| `FRONTEND_ORIGIN` | No | CORS origin (default port 8000) | Keep the default |
| `YOUTUBE_API_KEY` | For Trends | Reads YouTube trending data | Google Cloud Console → Credentials |
| `PEXELS_API_KEY` | For B-roll | Stock footage search in the Editor | pexels.com/api |
| `GOOGLE_YOUTUBE_CLIENT_ID`, `GOOGLE_YOUTUBE_CLIENT_SECRET`, `GOOGLE_YOUTUBE_REDIRECT_URI` | For YouTube publishing | Connect a channel and upload | Google Cloud Console → OAuth client |
| `SOCIAL_TOKEN_ENCRYPTION_KEY` | For YouTube publishing | Encrypts saved channel tokens | Generate: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SOCIAL_DATABASE_PATH` | No | Where publishing data is saved | Keep the default |
| `CASCADE_DEV_AUTH` | No (local only) | `1` = run without Clerk as `dev-user` on your own machine | Never in production |
| `CASCADE_WARM_MODELS` | No | `0` skips loading the search models at start (saves ~700 MB RAM, first search is slower) | Optional |
| `CASCADE_JOB_TIMEOUT`, `CASCADE_FFMPEG_TIMEOUT`, `CASCADE_EDITOR_PROVIDER`, `CASCADE_EDITOR_FFMPEG`, `OPENAI_SCENE_MODEL` | No | Tuning; defaults are fine | See comments in `.env.example` |

## Troubleshooting

- **`http proxy error` / `ECONNREFUSED` / `502` in the Vite terminal.** The backend isn't running on port 8000, or it's still starting. Start it (step 5) and wait for `Application startup complete`.
- **Servers stop as soon as you close something.** Run each server in its own terminal tab and leave the tab open. Commands run in a one-off chat or script shell don't keep running.
- **`Address already in use` (port 8000 or 5173).** An old server is still running. Find it with `lsof -nP -iTCP:8000 -sTCP:LISTEN` (or `:5173`), then `kill <PID>`. If Vite quietly picks 5174 instead, that's the same problem: stop the old one.
- **`/api/...` returns the React page's HTML.** Vite isn't proxying. Restart `npm run dev` after any change to `vite.config.js`, and make sure it was started from `frontend/`.
- **`403 Origin not allowed`.** The page's origin is missing from the allowed list. The default list in `authorized_parties()` (`app1.py`) includes ports 8000 and 5173. If your `.env` sets `CLERK_AUTHORIZED_PARTIES`, it replaces that default, so add `http://localhost:5173,http://127.0.0.1:5173` there.
- **`401 Please sign in first`.** The proxy works and the backend wants a signed-in user. Sign in, or set `CASCADE_DEV_AUTH=1` in your local `.env` and restart the backend. Credential-free loopback requests then use `dev-user`; existing credentials are still checked. `/api/auth-config` reports `dev_auth` for frontend support. Never enable this in production.
- **"Face model is missing" in the Editor's Fill mode.** Run `.venv/bin/python scripts/setup_reframe.py` (step 4).
- **`You are sending unauthenticated requests to the HF Hub` or `Redirects are currently not supported in MacOs`.** Harmless startup warnings; ignore them.
- **"Editing AI is not configured" in the Editor chat.** The Editor chat uses the `LLM_PROVIDER` key (or `CASCADE_EDITOR_PROVIDER` if you set it), and that key is missing or still the placeholder. Restart the backend after editing `.env`.
- **The React app breaks after `git pull`.** Run `npm install` in `frontend/` (packages may have changed), then `npm run dev` again.
