"""Top 8 events sent in by players, waiting for an admin to publish them.

One table in match_records.db, top8_event_submissions. A row starts as
"pending" and nothing about it is shown on the Top 8 page until an admin
approves it; the approval job then imports the event and marks the row
"approved" (or "failed" if the import did not work, so it can be retried).
A rejected row keeps the admin's note so the player can see why.
"""

import datetime
import json
import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH

STATUSES = ("pending", "importing", "approved", "rejected", "failed")

_COLUMNS = (
    "id", "event_url", "event_id", "title", "note", "submitter_id", "submitter_name", "submitter_provider",
    "status", "event_name", "event_date", "player_count", "review_note", "reviewed_by",
    "reviewed_at", "result", "created_at", "updated_at", "deck_urls",
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class EventSubmissionRepository:
    """Data access for top8_event_submissions."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS top8_event_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_url TEXT NOT NULL,
                event_id TEXT NOT NULL,
                title TEXT,
                note TEXT,
                submitter_id TEXT NOT NULL,
                submitter_name TEXT,
                submitter_provider TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                event_name TEXT,
                event_date TEXT,
                player_count INTEGER,
                review_note TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Added after the table first shipped: deck links in finishing order,
        # for events that only collected their top lists.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(top8_event_submissions)")}
        if "deck_urls" not in cols:
            conn.execute("ALTER TABLE top8_event_submissions ADD COLUMN deck_urls TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_top8_submissions_status ON top8_event_submissions(status)"
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _row(r) -> dict:
        row = dict(zip(_COLUMNS, r))
        try:
            row["result"] = json.loads(row["result"]) if row["result"] else None
        except ValueError:
            row["result"] = None
        try:
            row["deck_urls"] = json.loads(row["deck_urls"]) if row["deck_urls"] else []
        except ValueError:
            row["deck_urls"] = []
        return row

    def _select(self, where: str = "", params: tuple = ()) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM top8_event_submissions {where} ORDER BY id DESC",
            params,
        ).fetchall()
        conn.close()
        return [self._row(r) for r in rows]

    def create(self, event_url: str, event_id: str, title: str, note: str,
               submitter_id: str, submitter_name: str, submitter_provider: str | None = None, deck_urls: list[str] | None = None) -> dict:
        now = _now()
        conn = self._connect()
        cur = conn.execute(
            """INSERT INTO top8_event_submissions
               (event_url, event_id, title, note, submitter_id, submitter_name, submitter_provider,
                status, created_at, updated_at, deck_urls)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (event_url, event_id, title or None, note or None, str(submitter_id),
             submitter_name, submitter_provider, now, now,
             json.dumps(deck_urls) if deck_urls else None),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return self.get(new_id)

    def get(self, submission_id: int) -> dict | None:
        rows = self._select("WHERE id = ?", (submission_id,))
        return rows[0] if rows else None

    def list_all(self, status: str | None = None) -> list[dict]:
        if status:
            return self._select("WHERE status = ?", (status,))
        return self._select()

    def list_for_submitter(self, submitter_id: str) -> list[dict]:
        return self._select("WHERE submitter_id = ?", (str(submitter_id),))

    def open_for_event(self, event_id: str) -> dict | None:
        """A pending or importing submission of this sorcerytcg.com event, if any."""
        rows = self._select(
            "WHERE event_id = ? AND status IN ('pending', 'importing')", (event_id,)
        )
        return rows[0] if rows else None

    def count_open_for_submitter(self, submitter_id: str) -> int:
        conn = self._connect()
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM top8_event_submissions WHERE submitter_id = ? AND status = 'pending'",
            (str(submitter_id),),
        ).fetchone()
        conn.close()
        return n

    def count_pending(self) -> int:
        conn = self._connect()
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM top8_event_submissions WHERE status = 'pending'"
        ).fetchone()
        conn.close()
        return n

    def set_preview(self, submission_id: int, event_name: str | None, event_date: str | None,
                    player_count: int | None):
        conn = self._connect()
        conn.execute(
            """UPDATE top8_event_submissions
               SET event_name = ?, event_date = ?, player_count = ?, updated_at = ?
               WHERE id = ?""",
            (event_name, event_date, player_count, _now(), submission_id),
        )
        conn.commit()
        conn.close()

    def claim_for_import(self, submission_id: int, reviewed_by: str, review_note: str) -> bool:
        """Move a pending (or failed) submission to importing. False if someone got there first."""
        conn = self._connect()
        cur = conn.execute(
            """UPDATE top8_event_submissions
               SET status = 'importing', reviewed_by = ?, review_note = ?, reviewed_at = ?, updated_at = ?
               WHERE id = ? AND status IN ('pending', 'failed')""",
            (reviewed_by, review_note or None, _now(), _now(), submission_id),
        )
        conn.commit()
        changed = cur.rowcount == 1
        conn.close()
        return changed

    def finish(self, submission_id: int, status: str, result: dict | None = None,
               player_count: int | None = None):
        if status not in STATUSES:
            raise ValueError(f"Unknown status {status}")
        conn = self._connect()
        conn.execute(
            """UPDATE top8_event_submissions
               SET status = ?, result = ?, player_count = COALESCE(?, player_count), updated_at = ?
               WHERE id = ?""",
            (status, json.dumps(result) if result is not None else None, player_count,
             _now(), submission_id),
        )
        conn.commit()
        conn.close()

    def reject(self, submission_id: int, reviewed_by: str, review_note: str) -> bool:
        conn = self._connect()
        now = _now()
        cur = conn.execute(
            """UPDATE top8_event_submissions
               SET status = 'rejected', reviewed_by = ?, review_note = ?, reviewed_at = ?, updated_at = ?
               WHERE id = ? AND status IN ('pending', 'failed')""",
            (reviewed_by, review_note or None, now, now, submission_id),
        )
        conn.commit()
        changed = cur.rowcount == 1
        conn.close()
        return changed
