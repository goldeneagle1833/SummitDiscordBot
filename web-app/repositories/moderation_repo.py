"""Timeouts and bans taken from block/report alerts (web app side).

Same ``moderation_actions`` table as discord-bot/repositories/moderation_repo.py:
the bot writes rows when the owner presses Timeout / Ban in a DM, the web app
writes rows when an admin does it from the admin panel. The admin lists show
the latest action per player.

The bot alone owns ``moderation_alerts`` (which blocks/reports were DMed), so
it is not created here.
"""

import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class ModerationRepository:
    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self):
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id TEXT NOT NULL,
                    target_name TEXT,
                    action TEXT NOT NULL,
                    duration_minutes INTEGER,
                    duration_label TEXT,
                    reason TEXT,
                    source_kind TEXT,
                    source_ref TEXT,
                    by_id TEXT,
                    by_name TEXT,
                    via TEXT NOT NULL,
                    bot_done INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_moderation_actions_target
                ON moderation_actions (target_id)
            """)
            conn.commit()
        finally:
            conn.close()

    def log_action(self, *, target_id, action, via="web", target_name=None,
                   duration_minutes=None, duration_label=None, reason=None,
                   source_kind=None, source_ref=None, by_id=None, by_name=None,
                   bot_done=True) -> int:
        """Record an action. ``bot_done=False`` asks the bot to follow up
        (pairing blocks: pull them from the LFG queue and DM them)."""
        conn = self._get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO moderation_actions (
                    target_id, target_name, action, duration_minutes, duration_label,
                    reason, source_kind, source_ref, by_id, by_name, via, bot_done
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(target_id), target_name, action, duration_minutes, duration_label,
                    reason, source_kind, None if source_ref is None else str(source_ref),
                    None if by_id is None else str(by_id), by_name, via, 1 if bot_done else 0,
                ),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def latest_by_target(self, target_ids) -> dict[str, dict]:
        """Most recent action for each of ``target_ids``."""
        ids = sorted({str(t) for t in target_ids if t})
        if not ids:
            return {}
        conn = self._get_connection()
        try:
            marks = ",".join("?" * len(ids))
            rows = conn.execute(
                f"""
                SELECT m.* FROM moderation_actions m
                JOIN (
                    SELECT target_id, MAX(id) AS id FROM moderation_actions
                    WHERE target_id IN ({marks}) GROUP BY target_id
                ) last ON last.id = m.id
                """,
                ids,
            ).fetchall()
        finally:
            conn.close()
        return {
            row["target_id"]: {
                "action": row["action"],
                "duration_minutes": row["duration_minutes"],
                "duration_label": row["duration_label"],
                "by_name": row["by_name"],
                "via": row["via"],
                "created_at": row["created_at"],
            }
            for row in rows
        }


# Same as discord-bot/repositories/pairing_bans_repo.py BAN_DURATIONS.
PAIRING_BLOCK_DURATIONS = {
    "24h": ("24 hours", 24),
    "48h": ("48 hours", 48),
    "72h": ("72 hours", 72),
    "lifetime": ("Lifetime", None),
}


def set_pairing_block(db_path, *, user_id, user_name, by_id, by_name, reason, duration_key) -> str:
    """Store a pairing-service block, same table and shape as the bot's ``!ban``.

    Returns the duration label. The bot's matchmaking checks this table at
    every way into the pairing service.
    """
    from datetime import datetime, timedelta, timezone

    label, hours = PAIRING_BLOCK_DURATIONS[duration_key]
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=hours) if hours else None
    conn = sqlite3.connect(str(db_path or MATCH_RECORDS_DB_PATH))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pairing_bans (
                user_id TEXT PRIMARY KEY,
                user_name TEXT,
                banned_by_id TEXT NOT NULL,
                banned_by_name TEXT,
                reason TEXT NOT NULL,
                duration_label TEXT NOT NULL,
                banned_at TEXT NOT NULL,
                expires_at TEXT
            )
        """)
        conn.execute(
            """
            INSERT INTO pairing_bans
                (user_id, user_name, banned_by_id, banned_by_name, reason,
                 duration_label, banned_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_name = excluded.user_name,
                banned_by_id = excluded.banned_by_id,
                banned_by_name = excluded.banned_by_name,
                reason = excluded.reason,
                duration_label = excluded.duration_label,
                banned_at = excluded.banned_at,
                expires_at = excluded.expires_at
            """,
            (str(user_id), user_name, str(by_id), by_name, reason, label,
             now.isoformat(), expires.isoformat() if expires else None),
        )
        conn.commit()
    finally:
        conn.close()
    return label
