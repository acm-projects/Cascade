"""Import existing metadata into Neon without overwriting existing DB records.
Run with the API stopped: python migrate_metadata.py
"""
import json
from pathlib import Path

from dotenv import load_dotenv
from metadata_store import get_store


def migrate(store):
    imported = skipped = 0
    for path in sorted(store.root.rglob('*.json')):
        if not store.key(path):
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        if path.name == 'owner.json':
            data.setdefault('created_at', path.stat().st_mtime)
        changed = store.write(path, data, import_only=True)
        imported += changed
        skipped += not changed
    return {'imported': imported, 'already_present': skipped}


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    load_dotenv(root / '.env', override=True)
    store = get_store(root / 'video_jobs')
    if not store.database_url:
        raise SystemExit('Set DATABASE_URL and CASCADE_METADATA_STORE=neon (or auto) before migrating.')
    try:
        print(migrate(store))
    except Exception:
        raise SystemExit('Migration failed. Check database access and local JSON files. No existing records were overwritten.') from None
