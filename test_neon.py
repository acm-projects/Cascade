"""Read-only connection check using the secret root .env configuration."""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parent / '.env')
    url = os.getenv('DATABASE_URL', '').strip()
    if not url:
        raise SystemExit('DATABASE_URL is missing from .env.')
    try:
        with psycopg2.connect(url, sslmode='require', connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT NOW()')
                print('SUCCESS! Connected to Neon. Database time:', cur.fetchone()[0])
    except psycopg2.Error:
        raise SystemExit('Connection failed. Check DATABASE_URL and Neon connectivity.') from None


if __name__ == '__main__':
    main()
