import os
import json
import psycopg2

# ===== Database connection =====
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ===== Load JSON files =====
def load_json(file):
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)

users = load_json("tahsee.json")
banned = load_json("banned.json")

# ===== Insert users =====
for tg_id, username in users.items():
    cur.execute("""
        INSERT INTO users (telegram_id, chess_username)
        VALUES (%s, %s)
        ON CONFLICT (telegram_id) DO UPDATE SET chess_username = EXCLUDED.chess_username
    """, (int(tg_id), username))

# ===== Insert banned users =====
for tg_id in banned.keys():
    cur.execute("""
        INSERT INTO banned_users (telegram_id)
        VALUES (%s)
        ON CONFLICT DO NOTHING
    """, (int(tg_id),))

conn.commit()
cur.close()
conn.close()
print("✅ Migration completed!")
