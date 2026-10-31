# FastAPI backend

From the repository root:

```sh
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

`main.py` composes routers and startup hooks. `core/` owns auth/config/jobs/storage;
`routers/` handles HTTP; `services/` owns project/session operations; `database/`
owns metadata and SQL. Feature packages implement agents, editor, research,
search, transcription, and rendering.

See [the full map](../docs/codebase-layout.md),
[database setup](../docs/database/README.md), and [tests](../tests/README.md).
Root configuration and saved jobs are private runtime data.
