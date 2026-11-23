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

    def history(self, target_ids) -> dict[str, list[dict]]:
        """Every action for each of ``target_ids``, oldest first."""
        ids = sorted({str(t) for t in target_ids if t})
        if not ids:
            return {}
        conn = self._get_connection()
        try:
            marks = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT * FROM moderation_actions WHERE target_id IN ({marks}) ORDER BY id ASC",
                ids,
            ).fetchall()
        finally:
            conn.close()
        out: dict[str, list[dict]] = {}
        for row in rows:
            out.setdefault(row["target_id"], []).append(dict(row))
        return out

    def recent_actions(self, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        """Newest actions first, for the Mod Tools activity list."""
        conn = self._get_connection()
        try:
            total = conn.execute("SELECT COUNT(*) FROM moderation_actions").fetchone()[0]
            rows = conn.execute(
                """SELECT id, target_id, target_name, action, duration_minutes, duration_label,
                          reason, source_kind, source_ref, by_name, via, created_at
                   FROM moderation_actions ORDER BY id DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows], total

    def status_by_target(self, target_ids, db_path=None) -> dict[str, dict]:
        """What is in force right now for each player, as far as the website knows.

        Timeouts and bans come from the action log (one done straight in
        Discord without the bot or website isn't seen). Pairing blocks come
        from the bot's ``pairing_bans`` table, which is the source of truth.
        """
        from datetime import datetime, timedelta, timezone

        ids = sorted({str(t) for t in target_ids if t})
        now = datetime.now(timezone.utc)
        status = {i: {"timed_out_until": None, "banned": False, "pairing_block": None} for i in ids}
        for target, actions in self.history(ids).items():
            for a in actions:
                kind = a["action"]
                if kind == "timeout" and a["duration_minutes"]:
                    start = _parse_utc(a["created_at"])
                    if start:
                        until = start + timedelta(minutes=int(a["duration_minutes"]))
                        status[target]["timed_out_until"] = until if until > now else None
                elif kind == "remove_timeout":
                    status[target]["timed_out_until"] = None
                elif kind == "ban":
                    status[target]["banned"] = True
                elif kind == "unban":
                    status[target]["banned"] = False
        for s in status.values():
            if s["timed_out_until"]:
                s["timed_out_until"] = s["timed_out_until"].isoformat()
        for target, block in active_pairing_blocks(ids, db_path or self._db_path).items():
            status[target]["pairing_block"] = block
        return status


def _parse_utc(value):
    from datetime import datetime, timezone

    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def active_pairing_blocks(user_ids, db_path=None) -> dict[str, dict]:
    """Pairing blocks still in force for ``user_ids`` (expired ones are skipped)."""
    from datetime import datetime, timezone

    ids = sorted({str(u) for u in user_ids if u})
    if not ids:
        return {}
    conn = sqlite3.connect(str(db_path or MATCH_RECORDS_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        marks = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT user_id, duration_label, expires_at FROM pairing_bans WHERE user_id IN ({marks})",
            ids,
        ).fetchall()
    except sqlite3.OperationalError:
        return {}  # the bot hasn't made the table yet
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    out = {}
    for row in rows:
        expires = _parse_utc(row["expires_at"])
        if expires and expires <= now:
            continue
        out[row["user_id"]] = {"duration_label": row["duration_label"], "expires_at": row["expires_at"]}
    return out


def lift_pairing_block(db_path, user_id) -> bool:
    """Remove a pairing block early (same as the bot's ``!unban``)."""
    conn = sqlite3.connect(str(db_path or MATCH_RECORDS_DB_PATH))
    try:
        cur = conn.execute("DELETE FROM pairing_bans WHERE user_id = ?", (str(user_id),))
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


class ModeratorsRepository:
    """Discord IDs that get the website's Mod Tools tab.

    Moderators can read player reports and time out, ban or pairing-block
    players; nothing else. Admins add and remove them from Mod Tools.
    """

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS moderators (
                    discord_user_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    added_by_id TEXT,
                    added_by_name TEXT,
                    added_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def is_moderator(self, user_id) -> bool:
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT 1 FROM moderators WHERE discord_user_id = ?", (str(user_id),)
            ).fetchone() is not None
        finally:
            conn.close()

    def list(self) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT discord_user_id, display_name, added_by_name, added_at "
                "FROM moderators ORDER BY added_at, discord_user_id"
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def add(self, user_id, display_name=None, by_id=None, by_name=None) -> bool:
        """Add a moderator. Returns False if they were already one."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO moderators (discord_user_id, display_name, added_by_id, added_by_name) "
                "VALUES (?, ?, ?, ?)",
                (str(user_id), display_name, None if by_id is None else str(by_id), by_name),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def remove(self, user_id) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM moderators WHERE discord_user_id = ?", (str(user_id),))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


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
