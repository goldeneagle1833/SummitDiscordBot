"""Test that table is auto-created when missing"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from webapp_config import MATCH_RECORDS_DB_PATH
from repositories.match_confirmation import MatchConfirmationRepository

print("Testing auto-creation when table is missing...")

# Step 1: Temporarily rename the table (if it exists)
conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations'")
if cursor.fetchone():
    print("Renaming existing table to match_confirmations_backup...")
    cursor.execute("ALTER TABLE match_confirmations RENAME TO match_confirmations_backup")
    conn.commit()
conn.close()

# Step 2: Verify table doesn't exist
conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations'")
print(f"Table exists before repo init: {cursor.fetchone() is not None}")
conn.close()

# Step 3: Instantiate repository (should auto-create table)
print("\nInstantiating MatchConfirmationRepository...")
repo = MatchConfirmationRepository()
print("Repository created!")

# Step 4: Verify table now exists
conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations'")
exists = cursor.fetchone() is not None
print(f"Table exists after repo init: {exists}")

if exists:
    cursor.execute("PRAGMA table_info(match_confirmations)")
    columns = cursor.fetchall()
    print(f"[SUCCESS] Table auto-created with {len(columns)} columns")
else:
    print("[FAIL] Table was not auto-created")

# Step 5: Cleanup - restore original table
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations_backup'")
if cursor.fetchone():
    print("\nRestoring original table...")
    cursor.execute("DROP TABLE IF EXISTS match_confirmations")
    cursor.execute("ALTER TABLE match_confirmations_backup RENAME TO match_confirmations")
    conn.commit()
    print("Original table restored")

conn.close()
print("\nTest complete!")
