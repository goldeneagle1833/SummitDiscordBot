"""One-time script to rename 'Testing' event to 'Season 1' in elo.db."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "elo.db"


def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Show current events
    cur.execute("SELECT event_id, event_name, start_date, end_date, is_active FROM events ORDER BY start_date")
    rows = cur.fetchall()
    print("Current events:")
    for row in rows:
        status = "(ACTIVE)" if row[4] else ""
        print(f"  ID={row[0]}  name={row[1]!r}  start={row[2]}  end={row[3]}  {status}")

    # Rename Testing -> Season 1
    cur.execute("UPDATE events SET event_name = 'Season 1' WHERE event_name = 'Testing'")
    updated = cur.rowcount

    if updated:
        conn.commit()
        print(f"\nRenamed 'Testing' -> 'Season 1' ({updated} row(s) updated)")
    else:
        print("\nNo event named 'Testing' found - nothing to rename")

    # Show updated events
    cur.execute("SELECT event_id, event_name, start_date, end_date, is_active FROM events ORDER BY start_date")
    rows = cur.fetchall()
    print("\nUpdated events:")
    for row in rows:
        status = "(ACTIVE)" if row[4] else ""
        print(f"  ID={row[0]}  name={row[1]!r}  start={row[2]}  end={row[3]}  {status}")

    conn.close()


if __name__ == "__main__":
    main()
