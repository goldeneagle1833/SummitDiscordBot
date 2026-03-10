"""Initialize match_confirmations table in match_records.db"""
import sqlite3
from pathlib import Path
from webapp_config import MATCH_RECORDS_DB_PATH

# Read SQL script
with open('init_match_confirmations_table.sql', 'r') as f:
    sql_script = f.read()

# Execute script
conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
conn.executescript(sql_script)
conn.close()

print('[OK] match_confirmations table created successfully!')

# Verify table was created
conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations'")
result = cursor.fetchone()

if result:
    print('[OK] Table verified to exist')
    # Show table schema
    cursor.execute("PRAGMA table_info(match_confirmations)")
    columns = cursor.fetchall()
    print(f'\nTable has {len(columns)} columns:')
    for col in columns:
        print(f'  - {col[1]} ({col[2]})')
else:
    print('[ERROR] Table verification failed')

conn.close()
