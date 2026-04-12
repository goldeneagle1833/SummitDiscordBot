"""Quick script to check pending confirmations in the database."""
import sqlite3

conn = sqlite3.connect("match_records.db")
cursor = conn.cursor()

try:
    cursor.execute("""
        SELECT id, reporter_id, opponent_id, winner_global, loser_global,
               created_at, match_type
        FROM pending_confirmations
        ORDER BY created_at DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    if not rows:
        print("No pending confirmations found.")
    else:
        print(f"\n{len(rows)} most recent pending confirmations:\n")
        for row in rows:
            print(f"ID: {row[0]}")
            print(f"  Reporter ID: {row[1]}")
            print(f"  Opponent ID: {row[2]}")
            print(f"  Winner: {row[3]}")
            print(f"  Loser: {row[4]}")
            print(f"  Created: {row[5]}")
            print(f"  Match Type: {row[6]}")
            print()

except sqlite3.OperationalError as e:
    print(f"Error: {e}")
    print("Table might not exist yet.")
finally:
    conn.close()
