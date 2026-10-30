"""Durable publishing queue in the existing social SQLite database.

Migration is additive. SQLite + OS locks require a single shared local disk (not
NFS). Every worker must mount the same database, lock directory and media spool.
"""
import json
import time
import uuid
from contextlib import contextmanager
from backend.social_youtube import db, schedule_lock


@contextmanager
def database():
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS scheduled_posts (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, project TEXT NOT NULL,
            submission TEXT NOT NULL, status TEXT NOT NULL, next_run REAL NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0, document TEXT NOT NULL,
            UNIQUE(owner, submission))''')
        c.execute('CREATE INDEX IF NOT EXISTS scheduled_posts_due ON scheduled_posts(status,next_run)')
        c.execute('''CREATE TABLE IF NOT EXISTS publishing_attempts (
            id INTEGER PRIMARY KEY, job TEXT NOT NULL, at REAL NOT NULL,
            stage TEXT NOT NULL, outcome TEXT NOT NULL)''')
        c.commit()
        yield c


def get(key):
    with database() as c:
        row = c.execute('SELECT document FROM scheduled_posts WHERE id=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def existing(owner, submission):
    with database() as c:
        row = c.execute('SELECT document FROM scheduled_posts WHERE owner=? AND submission=?', (owner, submission)).fetchone()
    return json.loads(row[0]) if row else None


def create(record):
    record = {**record, 'id': str(uuid.uuid4()), 'revision': 0}
    with database() as c:
        c.execute('INSERT OR IGNORE INTO scheduled_posts VALUES (?,?,?,?,?,?,?,?)',
                  (record['id'], record['user'], record['pid'], record['submission_id'], record['status'], record['next_run'], 0, json.dumps(record)))
    return existing(record['user'], record['submission_id'])


def save(record, **updates):
    record.update(updates)
    record['revision'] += 1
    with database() as c:
        c.execute('UPDATE scheduled_posts SET status=?,next_run=?,revision=?,document=? WHERE id=?',
                  (record['status'], record['next_run'], record['revision'], json.dumps(record), record['id']))
    return record


def event(record, stage, outcome, now=None):
    with database() as c:
        c.execute('INSERT INTO publishing_attempts(job,at,stage,outcome) VALUES (?,?,?,?)', (record['id'], time.time() if now is None else now, stage, outcome))


def list_posts(owner, project):
    with database() as c:
        rows = c.execute('SELECT document FROM scheduled_posts WHERE owner=? AND project=? ORDER BY rowid DESC LIMIT 200', (owner, project)).fetchall()
    return [json.loads(row[0]) for row in rows]


def due(now):
    with database() as c:
        rows = c.execute("SELECT id FROM scheduled_posts WHERE status IN ('Preparing','Scheduled','Publishing') AND next_run<=? ORDER BY next_run LIMIT 100", (now,)).fetchall()
    return [row[0] for row in rows]


def job_lock(key):
    # Kernel releases this cross-process lock after a crash. Read status only
    # AFTER acquiring: a stale candidate can never execute twice concurrently.
    return schedule_lock('durable-publishing:'+key)


PUBLIC = {'id','pid','jid','index','platform','account_id','account_name','status','schedule','run_at','revision',
          'error','url','provider_id','created_at','media_sha256','media_size','title','caption','hashtags','cover_time','mode','attempts','prepared_at'}


def public(record):
    return {k: v for k,v in record.items() if k in PUBLIC}
