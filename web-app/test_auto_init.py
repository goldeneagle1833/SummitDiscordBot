"""Test automatic table initialization"""
import sqlite3
import os
import sys
from pathlib import Path

# Add web-app to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from webapp_config import MATCH_RECORDS_DB_PATH
from repositories.match_confirmation import MatchConfirmationRepository

print("Testing automatic table initialization...")
print(f"Database path: {MATCH_RECORDS_DB_PATH}")

# First, check current state
conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations'")
exists_before = cursor.fetchone() is not None
print(f"Table exists before: {exists_before}")
conn.close()

# Instantiate repository (should trigger _ensure_table_exists)
print("\nInstantiating MatchConfirmationRepository...")
repo = MatchConfirmationRepository()

# Check if table exists now
conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations'")
exists_after = cursor.fetchone() is not None
print(f"Table exists after: {exists_after}")

if exists_after:
    # Verify schema
    cursor.execute("PRAGMA table_info(match_confirmations)")
    columns = cursor.fetchall()
    print(f"\n[OK] Table has {len(columns)} columns")

    # Verify indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='match_confirmations'")
    indexes = cursor.fetchall()
    print(f"[OK] Table has {len(indexes)} indexes")

    print("\n✓ Automatic table initialization works!")
else:
    print("\n✗ Table was not created automatically")

conn.close()
