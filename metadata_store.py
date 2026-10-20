"""Neon-backed JSON metadata; media and model caches remain on disk/S3."""
import json
import hashlib
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

MIGRATIONS = Path(__file__).parent / 'migrations'
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
                        for migration in sorted(MIGRATIONS.glob('*.sql')):
                            cur.execute(migration.read_text(encoding='utf-8'))
                finally:
                    pool.putconn(conn)
            except Exception:
                pool.closeall()
                raise
            self.pool = pool

    @staticmethod
    def insert_user(cur, user_id):
        cur.execute('INSERT INTO cascade_app.users (clerk_user_id) VALUES (%s) '
                    'ON CONFLICT (clerk_user_id) DO NOTHING', (user_id,))

    def ensure_user(self, user_id):
        """Called with a verified Clerk subject, never email/password from a form."""
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError('A verified user ID is required')
        if self.database_url:
            with self.connection() as conn, conn.cursor() as cur:
                self.insert_user(cur, user_id)
        else:
            path = self.root / 'users' / (hashlib.sha256(user_id.encode()).hexdigest() + '.json')
            if not path.is_file():
                self.local_write(path, {'clerk_user_id': user_id, 'created_at': datetime.now(timezone.utc).isoformat()})

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
                if isinstance(data, dict) and data.get('user_id'):
                    self.insert_user(cur, data['user_id'])
                cur.execute('INSERT INTO cascade_app.records (key, payload) VALUES (%s, %s) ON CONFLICT (key) '
                            + conflict, (key, Json(data)))
                changed = cur.rowcount
                if not import_only and key.split('/')[-1] in {'owner.json', 'results.json'}:
                    cur.execute("""UPDATE cascade_app.records p SET
                        payload = jsonb_set(p.payload, '{updated_at}', to_jsonb(%s::double precision)),
                        updated_at = now()
                        FROM cascade_app.records o
                        WHERE o.key = %s AND p.key ~ '^projects/[0-9a-f]{64}/[0-9a-f]{32}\\.json$'
                          AND p.payload->>'id' = o.payload->>'project_id'
                          AND p.payload->>'user_id' = o.payload->>'user_id'""",
                        (time.time(), key.split('/')[0] + '/owner.json'))
            # Neon is authoritative. A failed local cache must not undo a committed save.
            if not import_only:
                try:
                    self.local_write(path, data)
                except OSError:
                    pass
            return changed
        self.local_write(path, data)
        if key and key.split('/')[-1] in {'owner.json', 'results.json'}:
            owner_path = path.parent / 'owner.json'
            if owner_path.is_file():
                owner = self.read(owner_path)
                if owner.get('user_id') and re.fullmatch('[0-9a-f]{32}', owner.get('project_id') or ''):
                    user_hash = hashlib.sha256(owner['user_id'].encode()).hexdigest()
                    project_path = self.root / 'projects' / user_hash / (owner['project_id'] + '.json')
                    if project_path.is_file():
                        self.update_project(project_path, owner['user_id'], {})
        return 1

    def update_project(self, path, user_id, changes):
        """Atomic JSON merge preserves saved clips when a project is renamed."""
        patch = {**changes, 'updated_at': time.time()}
        if self.database_url:
            from psycopg2.extras import Json
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute("""UPDATE cascade_app.records SET payload = payload || %s::jsonb, updated_at = now()
                    WHERE key = %s AND payload->>'user_id' = %s RETURNING payload""",
                    (Json(patch), self.key(path), user_id))
                row = cur.fetchone()
            if row is None:
                raise HTTPException(404, 'Project not found.')
            return row[0]
        data = self.read(path)
        if data.get('user_id') != user_id:
            raise HTTPException(404, 'Project not found.')
        data.update(patch)
        self.local_write(Path(path), data)
        return data

    def delete(self, path):
        key = self.key(path)
        if self.database_url and key:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM cascade_app.records WHERE key = %s', (key,))
        Path(path).unlink(missing_ok=True)

    def delete_project_metadata(self, path, user_id, job_ids, referenced):
        if not self.database_url:
            return
        from psycopg2.extras import Json
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cascade_app.records WHERE key = %s AND payload->>'user_id' = %s",
                        (self.key(path), user_id))
            for job_id in job_ids:
                if job_id in referenced:
                    cur.execute('UPDATE cascade_app.records SET payload = payload || %s::jsonb WHERE key = %s',
                                (Json({'project_deleted': True}), job_id + '/owner.json'))
                else:
                    cur.execute('DELETE FROM cascade_app.records WHERE key LIKE %s', (job_id + '/%',))

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
                data['updated_at'] = time.time()
                self.write(path, data)
            return
        from psycopg2.extras import Json
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE cascade_app.records
                SET payload = jsonb_set(jsonb_set(payload, '{saved_clips}',
                    COALESCE(payload->'saved_clips', '[]'::jsonb) || %s::jsonb),
                    '{updated_at}', %s::jsonb), updated_at = now()
                WHERE key = %s AND payload->>'user_id' = %s
                  AND NOT COALESCE(payload->'saved_clips', '[]'::jsonb) @> %s::jsonb""",
                (Json([entry]), Json(time.time()), self.key(path), user_id, Json([entry])))


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
