"""Standalone migration: Add missing columns to user_profiles table
No dependencies required - just specify database path directly.
"""
import sqlite3
import sys
from pathlib import Path

# Database path - modify if your database is in a different location
# Default: ../discord-bot/match_records.db (relative to web-app directory)
if len(sys.argv) > 1:
    DB_PATH = sys.argv[1]
else:
    # Default path (relative to web-app directory)
    DB_PATH = str(Path(__file__).parent.parent / "discord-bot" / "match_records.db")

print("=" * 60)
print("User Profiles Table Migration")
print("=" * 60)
print(f"Database: {DB_PATH}")

# Check if database exists
if not Path(DB_PATH).exists():
    print(f"\n[ERROR] Database not found at: {DB_PATH}")
    print("\nUsage: python3 migrate_user_profiles_standalone.py [/path/to/match_records.db]")
    sys.exit(1)

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if user_profiles table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'")
    if not cursor.fetchone():
        print("\n[ERROR] user_profiles table does not exist!")
        print("Create the table first before running this migration.")
        sys.exit(1)

    # Check current columns
    cursor.execute("PRAGMA table_info(user_profiles)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"\nCurrent columns ({len(existing_columns)}): {', '.join(sorted(existing_columns))}")

    # Define columns that should exist
    required_columns = {
        'email': 'TEXT',
        'email_verified': 'INTEGER',
        'discriminator': 'TEXT',
        'flags': 'INTEGER',
        'public_flags': 'INTEGER',
        'given_name': 'TEXT',
        'family_name': 'TEXT',
        'locale': 'TEXT',
        'raw_oauth_data': 'TEXT'
    }

    # Add missing columns
    missing_columns = []
    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            missing_columns.append((col_name, col_type))
            print(f"\n[+] Adding column: {col_name} ({col_type})")
            cursor.execute(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_type}")

    if missing_columns:
        conn.commit()
        print(f"\n{'=' * 60}")
        print(f"[SUCCESS] Added {len(missing_columns)} columns")
        print(f"{'=' * 60}")
    else:
        print(f"\n{'=' * 60}")
        print("[OK] All required columns already exist - no migration needed")
        print(f"{'=' * 60}")

    # Verify final schema
    cursor.execute("PRAGMA table_info(user_profiles)")
    final_columns = cursor.fetchall()
    print(f"\nFinal schema ({len(final_columns)} columns):")
    for col in final_columns:
        marker = "✓ NEW" if col[1] in [c[0] for c in missing_columns] else ""
        print(f"  - {col[1]:<20} {col[2]:<10} {marker}")

    conn.close()
    print(f"\n{'=' * 60}")
    print("Migration complete!")
    print(f"{'=' * 60}\n")

except sqlite3.Error as e:
    print(f"\n[ERROR] SQLite error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
