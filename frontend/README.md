# Cascade React frontend

From the repository root:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173 with FastAPI running on port 8000. Vite proxies API
and media requests to that backend. `src/pages/` owns routes, `src/features/`
groups product behavior, `src/api/` owns HTTP, and shared UI/styles/assets live
in their named folders. Tests stay beside React logic.

Run `npm --prefix frontend test`, `npm --prefix frontend run lint`, and
`npm --prefix frontend run build`. Test discovery includes the retained legacy
Studio graph tests. Lint/build target the current React client.

`legacy/` isolates the older website and its separate Studio bundle. It remains
served for compatibility; see [its README](legacy/README.md).
