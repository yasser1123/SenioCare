import sys
sys.path.insert(0, ".")

from seniocare.data.database import _initialize_database
print("Running _initialize_database()...")
_initialize_database()
print("Done!")

# Verify
import psycopg2, os
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ["APP_DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
rows = cur.fetchall()
print(f"Tables after init: {[r[0] for r in rows]}")

# Check row counts
for table in [r[0] for r in rows]:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  {table}: {count} rows")

conn.close()
