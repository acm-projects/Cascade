# Retained legacy frontend

The current React client lives in `frontend/src/`. This folder holds UI still
served by FastAPI and covered by compatibility tests:

- `web/`: consolidated Jinja template, scripts, styles, and built Studio assets.
  Existing legacy page URLs keep working.
- `studio-ui/`: React Flow source and build tool for `web/studio/`. From this
  folder, run `npm --prefix studio-ui ci` and `npm --prefix studio-ui run build`.

Retirement needs a separate route/feature-parity decision. `package.json`
declares CommonJS for older `.js` files; `studio-ui/` owns its ESM package.
