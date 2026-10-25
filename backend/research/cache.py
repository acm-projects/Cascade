"""Atomic JSON caches and a shared daily quota ledger, including process locking."""
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from backend.research import QuotaBudgetExceeded, ResearchConfigError

CACHE_DIR = Path(__file__).resolve().parent / '.cache' / 'research'
TTL = 24 * 60 * 60
_THREAD_LOCK = RLock()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False, suffix='.tmp') as out:
            name = out.name
            json.dump(value, out, ensure_ascii=False, allow_nan=False)
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


@contextmanager
def locked():
    # One ledger/cache directory is shared by all threads and local server workers.
    with _THREAD_LOCK:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with (CACHE_DIR / '.lock').open('a+b') as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def get(key):
    item = read_json(CACHE_DIR / (digest(key) + '.json'))
    if item and 0 <= time.time() - item.get('created_at', 0) < TTL:
        return item.get('data')
    return None


def put(key, data):
    write_json(CACHE_DIR / (digest(key) + '.json'), {'created_at': time.time(), 'data': data})


def reserve_units(units):
    if type(units) is not int or units <= 0:
        raise ValueError('Quota reservation must be a positive integer.')
    try:
        budget = int(os.getenv('RESEARCH_DAILY_UNIT_BUDGET', '8000'))
        if budget < 0: raise ValueError
    except ValueError:
        raise ResearchConfigError('RESEARCH_DAILY_UNIT_BUDGET must be a nonnegative integer.')
    with locked():
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        path = CACHE_DIR / 'quota.json'
        ledger = read_json(path)
        if ledger is None and path.exists():
            raise QuotaBudgetExceeded('Research quota ledger is unreadable. Restore it before making more requests.')
        if ledger is not None and (not isinstance(ledger, dict) or type(ledger.get('units')) is not int or ledger['units'] < 0
                                   or not isinstance(ledger.get('date'), str)):
            raise QuotaBudgetExceeded('Research quota ledger is invalid. Restore it before making more requests.')
        used = ledger.get('units', 0) if ledger and ledger.get('date') == today else 0
        if used + units > budget:
            raise QuotaBudgetExceeded('Daily research quota budget reached. Try again tomorrow or use cached results.')
        write_json(path, {'date': today, 'units': used + units})
