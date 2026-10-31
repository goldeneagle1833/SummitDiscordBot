"""Moderation alerts and actions in match_records.db (Discord bot side).

When a player blocks someone (Summit profile or Play Sorcery Online) or files
a player report (Report Player button or Play Sorcery Online), the bot DMs the
owner with the details and Timeout / Ban buttons.

``moderation_alerts`` remembers which blocks and reports have already been
sent, so each one is DMed once. ``moderation_actions`` records every timeout
and ban taken from the DM or the website admin panel; the web app reads and
writes the same table (web-app/repositories/moderation_repo.py).
"""

import json
import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"

KIND_BLOCK = "block"
KIND_REPORT = "report"


@contextmanager
def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def block_key(row) -> str:
    """Stable key for one block. A block removed and added again is new."""
    return f"{row['user_id']}|{row['blocked_user_id']}|{row['created_at']}"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def create_moderation_tables():
    """Create the alert and action tables.

    The first time the alert table is created, every block and report that
    already exists is marked as sent, so turning this on does not DM the
    owner the whole history.
    """
    with _get_connection() as conn:
        first_run = not _table_exists(conn, "moderation_alerts")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_alerts (
                kind TEXT NOT NULL,
                ref TEXT NOT NULL,
                alerted_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (kind, ref)
            )
        """)
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
        if first_run:
            seeded = 0
            if _table_exists(conn, "blocked_users"):
                for row in conn.execute(
                    "SELECT user_id, blocked_user_id, created_at FROM blocked_users"
                ).fetchall():
                    conn.execute(
                        "INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES (?, ?)",
                        (KIND_BLOCK, block_key(row)),
                    )
                    seeded += 1
            if _table_exists(conn, "player_reports"):
                for row in conn.execute("SELECT id FROM player_reports").fetchall():
                    conn.execute(
                        "INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES (?, ?)",
                        (KIND_REPORT, str(row["id"])),
                    )
                    seeded += 1
            logger.info("Moderation alerts: marked %s existing blocks/reports as sent", seeded)


def _reasons(raw) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def get_unsent_blocks(limit: int = 10) -> list[dict]:
    """Blocks that have not been DMed yet, oldest first."""
    with _get_connection() as conn:
        if not _table_exists(conn, "blocked_users"):
            return []
        rows = conn.execute(
            """
            SELECT b.user_id, b.blocked_user_id, b.reason, b.created_at
            FROM blocked_users b
            LEFT JOIN moderation_alerts a
              ON a.kind = 'block'
             AND a.ref = b.user_id || '|' || b.blocked_user_id || '|' || b.created_at
            WHERE a.ref IS NULL
            ORDER BY b.created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_unsent_reports(limit: int = 10) -> list[dict]:
    """Player reports that have not been DMed yet, oldest first."""
    with _get_connection() as conn:
        if not _table_exists(conn, "player_reports"):
            return []
        has_source = any(
            col["name"] == "source"
            for col in conn.execute("PRAGMA table_info(player_reports)").fetchall()
        )
        source_col = "r.source" if has_source else "NULL AS source"
        rows = conn.execute(
            f"""
            SELECT r.id, r.reporter_id, r.reporter_name, r.reported_id, r.reported_name,
                   r.pairing_id, r.match_type, r.reasons, r.details, {source_col}, r.created_at
            FROM player_reports r
            LEFT JOIN moderation_alerts a
              ON a.kind = 'report' AND a.ref = CAST(r.id AS TEXT)
            WHERE a.ref IS NULL
            ORDER BY r.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            entry = dict(row)
            entry["reasons"] = _reasons(row["reasons"])
            result.append(entry)
        return result


def get_report(report_id: int) -> dict | None:
    with _get_connection() as conn:
        if not _table_exists(conn, "player_reports"):
            return None
        row = conn.execute("SELECT * FROM player_reports WHERE id = ?", (int(report_id),)).fetchone()
        if not row:
            return None
        entry = dict(row)
        entry["reasons"] = _reasons(row["reasons"])
        return entry


def mark_alerted(kind: str, ref: str):
    with _get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES (?, ?)",
            (kind, str(ref)),
        )


def log_moderation_action(
    *,
    target_id,
    action: str,
    via: str,
    target_name=None,
    duration_minutes=None,
    duration_label=None,
    reason=None,
    source_kind=None,
    source_ref=None,
    by_id=None,
    by_name=None,
) -> int:
    """Record a timeout, ban or pairing block. Returns the new row id."""
    with _get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO moderation_actions (
                target_id, target_name, action, duration_minutes, duration_label, reason,
                source_kind, source_ref, by_id, by_name, via
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(target_id), target_name, action, duration_minutes, duration_label, reason,
                source_kind, None if source_ref is None else str(source_ref),
                None if by_id is None else str(by_id), by_name, via,
            ),
        )
        return cur.lastrowid


def get_pending_web_pairing_blocks(limit: int = 10) -> list[dict]:
    """Pairing blocks set from the website that the bot hasn't followed up yet.

    The website stores the block itself; the bot still has to pull the player
    out of the in-memory LFG queue and DM them, like ``!ban`` does.
    """
    with _get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM moderation_actions
               WHERE action = 'pairing_block' AND bot_done = 0
               ORDER BY id ASC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_bot_done(action_id: int):
    with _get_connection() as conn:
        conn.execute("UPDATE moderation_actions SET bot_done = 1 WHERE id = ?", (int(action_id),))


def get_actions_for_target(target_id) -> list[dict]:
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM moderation_actions WHERE target_id = ? ORDER BY id DESC",
            (str(target_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def get_profile_name(user_id) -> str | None:
    """Website display name for a player id, if they have a profile."""
    with _get_connection() as conn:
        if not _table_exists(conn, "user_profiles"):
            return None
        row = conn.execute(
            "SELECT display_name FROM user_profiles WHERE user_id = ?", (str(user_id),)
        ).fetchone()
        return row["display_name"] if row and row["display_name"] else None


def get_history_counts(target_id) -> dict:
    """How many reports and blocks a player has against them in total."""
    target_id = str(target_id)
    with _get_connection() as conn:
        reports = blocks = 0
        if _table_exists(conn, "player_reports"):
            reports = conn.execute(
                "SELECT COUNT(*) FROM player_reports WHERE reported_id = ?", (target_id,)
            ).fetchone()[0]
        if _table_exists(conn, "blocked_users"):
            blocks = conn.execute(
                "SELECT COUNT(*) FROM blocked_users WHERE blocked_user_id = ?", (target_id,)
            ).fetchone()[0]
        return {"reports": reports, "blocks": blocks}
