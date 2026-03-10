"""Migration: Add missing columns to user_profiles table"""
import sqlite3
from webapp_config import MATCH_RECORDS_DB_PATH

print("Migrating user_profiles table...")
print(f"Database: {MATCH_RECORDS_DB_PATH}")

conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
cursor = conn.cursor()

# Check current columns
cursor.execute("PRAGMA table_info(user_profiles)")
existing_columns = {row[1] for row in cursor.fetchall()}
print(f"\nExisting columns: {existing_columns}")

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
        print(f"Adding column: {col_name} ({col_type})")
        cursor.execute(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_type}")

if missing_columns:
    conn.commit()
    print(f"\n[OK] Added {len(missing_columns)} columns")
else:
    print("\n[OK] All columns already exist")

# Verify final schema
cursor.execute("PRAGMA table_info(user_profiles)")
final_columns = cursor.fetchall()
print(f"\nFinal schema ({len(final_columns)} columns):")
for col in final_columns:
    print(f"  - {col[1]} ({col[2]})")

conn.close()
print("\nMigration complete!")
