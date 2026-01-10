import sqlite3

conn = sqlite3.connect("../fart_scores.db")
cursor = conn.cursor()

print("Tables:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
print(cursor.fetchall())

print("\nTable structure:")
cursor.execute("PRAGMA table_info(fart_scores)")
for row in cursor.fetchall():
    print(row)

print("\nSample data:")
cursor.execute("SELECT * FROM fart_scores ORDER BY score DESC LIMIT 10")
for row in cursor.fetchall():
    print(row)

conn.close()
