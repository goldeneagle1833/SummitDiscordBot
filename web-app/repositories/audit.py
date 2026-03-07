"""Repository for admin audit log access."""

import datetime
import json
import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class AuditRepository:
    """Data access for admin_audit_log table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get_logs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Fetch audit log entries, newest first."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, timestamp, admin_id, admin_name, action,
                      target_id, target_name, previous_state, new_state, details
               FROM admin_audit_log
               ORDER BY id DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        columns = [
            "id", "timestamp", "admin_id", "admin_name", "action",
            "target_id", "target_name", "previous_state", "new_state", "details",
        ]
        rows = []
        for row in cur.fetchall():
            entry = dict(zip(columns, row))
            # Parse JSON fields for display
            if entry["previous_state"]:
                try:
                    entry["previous_state"] = json.loads(entry["previous_state"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if entry["new_state"]:
                try:
                    entry["new_state"] = json.loads(entry["new_state"])
                except (json.JSONDecodeError, TypeError):
                    pass
            rows.append(entry)
        conn.close()
        return rows

    def get_log_count(self) -> int:
        """Get total number of audit log entries."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM admin_audit_log")
        count = cur.fetchone()[0]
        conn.close()
        return count

    def log_action(self, admin_id, admin_name, action, target_id=None,
                   target_name=None, previous_state=None, new_state=None,
                   details=None):
        """Write an audit log entry (used by web app admin routes)."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO admin_audit_log
               (timestamp, admin_id, admin_name, action, target_id,
                target_name, previous_state, new_state, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.datetime.now().isoformat(),
                admin_id,
                admin_name,
                action,
                str(target_id) if target_id is not None else None,
                target_name,
                json.dumps(previous_state) if previous_state else None,
                json.dumps(new_state) if new_state else None,
                details,
            ),
        )
        conn.commit()
        conn.close()
