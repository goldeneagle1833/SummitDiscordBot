import sqlite3
import os

db_path = r"F:\GitHub\SummitDiscordBot\discord-bot\elo.db"
print(f"Checking if file exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables in elo.db:", tables)

for table in tables:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    print(f"\n{table} columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")

conn.close()
