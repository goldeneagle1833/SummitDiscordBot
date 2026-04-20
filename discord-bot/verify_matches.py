#!/usr/bin/env python3
"""
Script to verify recent matches are being saved correctly.
Run this ON THE SERVER where the bot is running.
"""
import sqlite3
import sys
from pathlib import Path

def check_recent_matches():
    """Check if matches from the last 24 hours are being saved."""
    try:
        db_path = Path("match_records.db")
        if not db_path.exists():
            print(f"❌ Database not found at {db_path.absolute()}")
            return False

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        # Check table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_records'"
        )
        if not cur.fetchone():
            print("❌ match_records table does not exist!")
            conn.close()
            return False

        # Get column names
        cur.execute("PRAGMA table_info(match_records)")
        columns = {row[1] for row in cur.fetchall()}
        print(f"✓ Table columns: {', '.join(sorted(columns))}\n")

        # Count total matches
        cur.execute("SELECT COUNT(*) FROM match_records")
        total = cur.fetchone()[0]
        print(f"Total matches in database: {total}")

        # Get recent matches (last 24 hours)
        cur.execute("""
            SELECT rowid, winner_id, losser_id, timestamp,
                   winner_elo_change, loser_elo_change, match_type
            FROM match_records
            WHERE timestamp >= datetime('now', '-24 hours')
            ORDER BY rowid DESC
            LIMIT 20
        """)
        recent = cur.fetchall()

        if recent:
            print(f"\n✓ Found {len(recent)} matches in the last 24 hours:\n")
            for row in recent:
                match_id, winner_id, loser_id, timestamp, w_elo, l_elo, match_type = row
                print(f"  Match #{match_id}: Winner={winner_id}, Loser={loser_id}")
                print(f"    Time: {timestamp}, Type: {match_type or 'ranked'}")
                print(f"    ELO changes: Winner {w_elo:+}, Loser {l_elo:+}\n")
        else:
            print("\n⚠️  No matches found in the last 24 hours")

        # Check for specific player's matches
        print("\n--- Check specific player ---")
        print("Enter a Discord user ID to see their recent matches (or press Enter to skip):")
        user_id = input().strip()

        if user_id:
            cur.execute("""
                SELECT rowid, winner_id, losser_id, timestamp
                FROM match_records
                WHERE winner_id = ? OR losser_id = ?
                ORDER BY rowid DESC
                LIMIT 10
            """, (user_id, user_id))

            player_matches = cur.fetchall()
            if player_matches:
                print(f"\n✓ Found {len(player_matches)} recent matches for user {user_id}:")
                for row in player_matches:
                    match_id, winner_id, loser_id, timestamp = row
                    result = "WON" if winner_id == int(user_id) else "LOST"
                    opponent = loser_id if winner_id == int(user_id) else winner_id
                    print(f"  Match #{match_id}: {result} vs {opponent} at {timestamp}")
            else:
                print(f"\n❌ No matches found for user {user_id}")

        conn.close()
        return True

    except sqlite3.DatabaseError as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== Match Records Verification ===\n")
    success = check_recent_matches()
    sys.exit(0 if success else 1)
