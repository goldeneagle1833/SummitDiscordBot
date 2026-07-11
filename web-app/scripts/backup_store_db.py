#!/usr/bin/env python3
"""Nightly rotating backup of store.db using SQLite's online backup API.

Safe to run while the web app is live. Keeps the most recent N snapshots.

Usage:
    python scripts/backup_store_db.py [--dest /path/to/backups] [--keep 14]

Cron example (2:15 AM daily):
    15 2 * * * cd /path/to/web-app && /usr/bin/python3 scripts/backup_store_db.py

Pulling backups to your local machine (run FROM your local machine):
    rsync -avz user@yourserver:/path/to/web-app/backups/store/ ~/SummitBackups/store/
Or on Windows, use WinSCP scheduled sync, or just use the
"Download backup" button in the store admin page.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repositories.store import STORE_DB_PATH  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Backup store.db with rotation")
    parser.add_argument("--dest", type=Path,
                        default=Path(__file__).resolve().parent.parent / "backups" / "store")
    parser.add_argument("--keep", type=int, default=14,
                        help="Number of snapshots to retain (default 14)")
    args = parser.parse_args()

    if not Path(STORE_DB_PATH).exists():
        print(f"Source database not found: {STORE_DB_PATH}")
        sys.exit(1)

    args.dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = args.dest / f"store-{stamp}.db"

    src = sqlite3.connect(STORE_DB_PATH)
    dest = sqlite3.connect(target)
    try:
        with dest:
            src.backup(dest)
    finally:
        dest.close()
        src.close()

    # Verify the snapshot is a readable SQLite file before rotating old ones
    check = sqlite3.connect(target)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            print(f"WARNING: integrity check failed on {target}: {result[0]}")
            sys.exit(2)
    finally:
        check.close()

    print(f"Backup written: {target}")

    snapshots = sorted(args.dest.glob("store-*.db"))
    excess = len(snapshots) - args.keep
    for old in snapshots[:max(excess, 0)]:
        old.unlink()
        print(f"Rotated out: {old.name}")


if __name__ == "__main__":
    main()
