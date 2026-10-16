"""Neon-backed JSON metadata; media and model caches remain on disk/S3."""
import json
import os
import re
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

SCHEMA = Path(__file__).parent / 'migrations' / '001_metadata.sql'
JOB_FILES = {'owner.json', 'results.json', 'progress.json', 'failure.json'}


class MetadataStore:
    def __init__(self, root, database_url=None):
        self.root = Path(root).resolve()
        self.database_url = database_url
        self.pool = None
        self.init_lock = Lock()

    def key(self, path):
        try:
            key = Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return None
        parts = key.split('/')
        if (len(parts) == 2 and re.fullmatch('[0-9a-f]{32}', parts[0]) and parts[1] in JOB_FILES):
            return key
        if (len(parts) == 3 and parts[0] == 'projects' and re.fullmatch('[0-9a-f]{64}', parts[1])
                and re.fullmatch('[0-9a-f]{32}\\.json', parts[2])):
            return key
        if (len(parts) == 4 and parts[0] == 'projects' and re.fullmatch('[0-9a-f]{64}', parts[1])
                and parts[2:] == ['settings', 'preferences.json']):
            return key
        return None

    @contextmanager
    def connection(self):
        conn = None
        try:
            self.initialize()
            conn = self.pool.getconn()
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL statement_timeout = '10s'; SET LOCAL lock_timeout = '5s'")
                yield conn
        except Exception:
            # Driver errors can contain connection details. Never expose them.
            raise HTTPException(503, 'Database unavailable. Check the API database configuration and retry.') from None
        finally:
            if conn is not None:
                self.pool.putconn(conn, close=bool(conn.closed))

    def initialize(self):
        if not self.database_url or self.pool is not None:
            return
        from psycopg2.pool import ThreadedConnectionPool
        with self.init_lock:
            if self.pool is not None:
                return
            pool = ThreadedConnectionPool(1, 8, self.database_url, sslmode='require', connect_timeout=10)
            try:
                conn = pool.getconn()
                try:
                    with conn, conn.cursor() as cur:
                        cur.execute("SET LOCAL statement_timeout = '10s'; SET LOCAL lock_timeout = '5s'")
                        cur.execute(SCHEMA.read_text(encoding='utf-8'))
                finally:
                    pool.putconn(conn)
            except Exception:
                pool.closeall()
                raise
            self.pool = pool

    def read(self, path):
        key = self.key(path)
        if self.database_url and key:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute('SELECT payload FROM cascade_app.records WHERE key = %s', (key,))
                row = cur.fetchone()
            if row is None:
                raise FileNotFoundError('Metadata record not found')
            return row[0]
        return json.loads(Path(path).read_text(encoding='utf-8'))

    def exists(self, path):
        if self.database_url and self.key(path):
            try:
                self.read(path)
                return True
            except FileNotFoundError:
                return False
        return Path(path).is_file()

    def write(self, path, data, *, import_only=False):
        from psycopg2.extras import Json
        path = Path(path)
        key = self.key(path)
        if self.database_url and key:
            conflict = 'DO NOTHING' if import_only else 'DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()'
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute('INSERT INTO cascade_app.records (key, payload) VALUES (%s, %s) ON CONFLICT (key) '
                            + conflict, (key, Json(data)))
                changed = cur.rowcount
            # Neon is authoritative. A failed local cache must not undo a committed save.
            if not import_only:
                try:
                    self.local_write(path, data)
                except OSError:
                    pass
            return changed
        self.local_write(path, data)
        return 1

    @staticmethod
    def local_write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def documents(self, pattern, user_id=None):
        if not self.database_url:
            rows = [(path, self.read(path)) for path in self.root.glob(pattern)]
            return [(path, data) for path, data in rows if user_id is None or data.get('user_id') == user_id]
        # SQL narrows the prefix; the regex makes '*' match one path component only.
        prefix = pattern.split('*', 1)[0].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        regex = re.compile('^' + re.escape(pattern).replace(r'\*', '[^/]*') + '$')
        with self.connection() as conn, conn.cursor() as cur:
            query = 'SELECT key, payload FROM cascade_app.records WHERE key LIKE %s'
            args = [prefix + '%']
            if user_id is not None:
                query += " AND payload->>'user_id' = %s"
                args.append(user_id)
            cur.execute(query, args)
            return [(self.root / key, data) for key, data in cur.fetchall() if regex.fullmatch(key)]

    def paths(self, pattern):
        return [path for path, data in self.documents(pattern)]

    def append_saved_clip(self, path, user_id, entry):
        if not self.database_url:
            data = self.read(path)
            if entry not in data['saved_clips']:
                data['saved_clips'].append(entry)
                self.write(path, data)
            return
        from psycopg2.extras import Json
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE cascade_app.records
                SET payload = jsonb_set(payload, '{saved_clips}',
                    COALESCE(payload->'saved_clips', '[]'::jsonb) || %s::jsonb), updated_at = now()
                WHERE key = %s AND payload->>'user_id' = %s
                  AND NOT COALESCE(payload->'saved_clips', '[]'::jsonb) @> %s::jsonb""",
                (Json([entry]), self.key(path), user_id, Json([entry])))


@lru_cache(maxsize=8)
def _store(root, database_url):
    return MetadataStore(root, database_url)


def get_store(root):
    mode = os.getenv('CASCADE_METADATA_STORE', 'auto').lower()
    if mode not in {'auto', 'local', 'neon'}:
        raise HTTPException(503, 'CASCADE_METADATA_STORE must be auto, local, or neon.')
    url = os.getenv('DATABASE_URL', '').strip() if mode != 'local' else ''
    if mode == 'neon' and not url:
        raise HTTPException(503, 'DATABASE_URL is required for Neon metadata storage.')
    return _store(str(Path(root).resolve()), url or None)
