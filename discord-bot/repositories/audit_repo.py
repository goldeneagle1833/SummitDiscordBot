"""Repository for admin action audit logging."""

import json
import datetime
import sqlite3
from contextlib import contextmanager


@contextmanager
def _get_connection():
    """Context manager for match_records.db connections."""
    conn = sqlite3.connect("match_records.db")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_audit_table():
    """Create the admin_audit_log table if it doesn't exist."""
    with _get_connection() as conn:
        conn.cursor().execute("""CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            admin_id INTEGER NOT NULL,
            admin_name TEXT NOT NULL,
            action TEXT NOT NULL,
            target_id TEXT,
            target_name TEXT,
            previous_state TEXT,
            new_state TEXT,
            details TEXT
        )""")


def log_admin_action(admin_id, admin_name, action, target_id=None,
                     target_name=None, previous_state=None, new_state=None,
                     details=None):
    """Log an admin action to the audit table.

    Parameters
    ----------
    admin_id : int
        Discord user ID of the admin performing the action.
    admin_name : str
        Display name of the admin.
    action : str
        Action identifier (e.g. "spot_elo_reset", "remove_match").
    target_id : str | int | None
        ID of the affected user or match.
    target_name : str | None
        Display name of the target.
    previous_state : dict | None
        State before the change (stored as JSON).
    new_state : dict | None
        State after the change (stored as JSON).
    details : str | None
        Human-readable summary of what happened.
    """
    with _get_connection() as conn:
        conn.cursor().execute(
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


def get_audit_logs(limit=100, offset=0):
    """Fetch audit log entries, newest first.

    Returns a list of dicts.
    """
    with _get_connection() as conn:
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
        return [dict(zip(columns, row)) for row in cur.fetchall()]
