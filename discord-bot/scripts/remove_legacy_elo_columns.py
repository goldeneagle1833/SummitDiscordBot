"""Migration: remove legacy elo / event_elo columns from overall_standings.

Run this script ONCE on the live elo.db BEFORE deploying the Phase 5 code changes.
Always back up elo.db first.

Steps:
  1. Back-fill: copy legacy values into online_ columns for any player whose
     online_ column is still at the 1500 default but the legacy column has history.
  2. Verify: assert that elo == online_elo and event_elo == online_event_elo for
     every row.  Prints a diff and aborts if any mismatch is found.
  3. Recreate: rebuild overall_standings without the legacy columns.

Usage:
    cd discord-bot
    python scripts/remove_legacy_elo_columns.py [--dry-run] [--db-path PATH]
"""

import argparse
import sqlite3
import sys


def run(db_path: str, dry_run: bool) -> None:
    print(f"Opening {db_path}  (dry_run={dry_run})")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Step 0: confirm the table has the legacy columns ──
    cur.execute("PRAGMA table_info(overall_standings)")
    columns = {row["name"] for row in cur.fetchall()}
    missing = {"elo", "event_elo", "online_elo", "online_event_elo"} - columns
    if missing:
        print(f"ERROR: columns missing from overall_standings: {missing}")
        conn.close()
        sys.exit(1)

    # ── Step 1: back-fill ──
    cur.execute(
        "UPDATE overall_standings SET online_elo = elo WHERE online_elo = 1500 AND elo != 1500"
    )
    backfill_online_elo = cur.rowcount
    cur.execute(
        "UPDATE overall_standings SET online_event_elo = event_elo "
        "WHERE online_event_elo = 1500 AND event_elo != 1500"
    )
    backfill_online_event_elo = cur.rowcount
    print(f"Back-fill: online_elo updated for {backfill_online_elo} rows")
    print(f"Back-fill: online_event_elo updated for {backfill_online_event_elo} rows")

    # ── Step 2: verify ──
    cur.execute(
        "SELECT user_id, user_display_name, elo, online_elo, event_elo, online_event_elo "
        "FROM overall_standings "
        "WHERE elo != online_elo OR event_elo != online_event_elo"
    )
    mismatches = cur.fetchall()
    if mismatches:
        print("\nERROR: column mismatch found — aborting before table rebuild:")
        for row in mismatches:
            print(
                f"  user_id={row['user_id']} ({row['user_display_name']}): "
                f"elo={row['elo']} online_elo={row['online_elo']} | "
                f"event_elo={row['event_elo']} online_event_elo={row['online_event_elo']}"
            )
        conn.rollback()
        conn.close()
        sys.exit(1)
    print("Verify: all rows match — safe to proceed")

    if dry_run:
        print("\nDry run complete — no changes committed.")
        conn.rollback()
        conn.close()
        return

    # ── Step 3: rebuild table without legacy columns ──
    cur.execute("""
        CREATE TABLE overall_standings_new (
            user_id           INTEGER PRIMARY KEY,
            user_display_name TEXT,
            online_elo        INTEGER DEFAULT 1500,
            online_event_elo  INTEGER DEFAULT 1500,
            paper_elo         INTEGER DEFAULT 1500,
            paper_event_elo   INTEGER DEFAULT 1500
        )
    """)

    cur.execute("""
        INSERT INTO overall_standings_new (
            user_id, user_display_name,
            online_elo, online_event_elo,
            paper_elo, paper_event_elo
        )
        SELECT
            user_id, user_display_name,
            online_elo, online_event_elo,
            COALESCE(paper_elo, 1500),
            COALESCE(paper_event_elo, 1500)
        FROM overall_standings
    """)
    rows_copied = cur.rowcount

    cur.execute("DROP TABLE overall_standings")
    cur.execute("ALTER TABLE overall_standings_new RENAME TO overall_standings")

    conn.commit()
    conn.close()
    print(f"Migration complete: {rows_copied} rows copied to new schema.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove legacy ELO columns from elo.db")
    parser.add_argument("--db-path", default="elo.db", help="Path to elo.db (default: elo.db)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Run steps 1-2 without committing step 3"
    )
    args = parser.parse_args()
    run(args.db_path, args.dry_run)
