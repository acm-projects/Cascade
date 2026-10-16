import psycopg2

# Wrapped in quotation marks!
db_url = "postgresql://neondb_owner:npg_Kb2jro1HBiAm@ep-silent-resonance-b5637vsw-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

print("Attempting to connect to Neon...")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT NOW();")
    db_time = cur.fetchone()
    print(f"SUCCESS! Connected to Neon. Current database time: {db_time}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Connection failed: {e}")
