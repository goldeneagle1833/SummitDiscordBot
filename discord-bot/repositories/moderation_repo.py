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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_group_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                source_kind TEXT,
                source_ref TEXT,
                opened_by_id TEXT,
                opened_by_name TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at TEXT,
                closed_by_name TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                note TEXT NOT NULL,
                by_id TEXT,
                by_name TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_moderation_notes_target ON moderation_notes (target_id)
        """)
        # Website Mod Tools page asks the bot to post a player summary in the mod
        # channel, and (admins) to flip match results; the bot works the queue.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_summary_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                requested_by_id TEXT,
                requested_by_name TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                done_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_match_flips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                requested_by_id TEXT,
                requested_by_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                done_at TEXT
            )
        """)
        for col in ("transcript TEXT", "message_count INTEGER"):
            try:
                conn.execute(f"ALTER TABLE moderation_group_chats ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
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


# ── group chats (private channel with the player + moderators who join) ──


def get_open_group_chat(target_id) -> dict | None:
    """The player's open group chat, if any. One open chat per player."""
    with _get_connection() as conn:
        if not _table_exists(conn, "moderation_group_chats"):
            return None
        row = conn.execute(
            "SELECT * FROM moderation_group_chats WHERE target_id = ? AND closed_at IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (str(target_id),),
        ).fetchone()
        return dict(row) if row else None


def get_group_chat_by_channel(channel_id) -> dict | None:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM moderation_group_chats WHERE channel_id = ? ORDER BY id DESC LIMIT 1",
            (str(channel_id),),
        ).fetchone()
        return dict(row) if row else None


def save_group_chat(*, target_id, channel_id, source_kind, source_ref, opened_by_id, opened_by_name) -> int:
    with _get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO moderation_group_chats "
            "(target_id, channel_id, source_kind, source_ref, opened_by_id, opened_by_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(target_id), str(channel_id), source_kind, str(source_ref or ""),
             str(opened_by_id), opened_by_name),
        )
        return cur.lastrowid


def close_group_chat(channel_id, closed_by_name=None, transcript=None, message_count=None):
    with _get_connection() as conn:
        conn.execute(
            "UPDATE moderation_group_chats SET closed_at = datetime('now'), closed_by_name = ?, "
            "transcript = COALESCE(?, transcript), message_count = COALESCE(?, message_count) "
            "WHERE channel_id = ? AND closed_at IS NULL",
            (closed_by_name, transcript, message_count, str(channel_id)),
        )


def is_site_moderator(user_id) -> bool:
    """Moderators Bruce adds on the website's Mod Tools page (by Discord ID).

    The table belongs to the web app; until it exists nobody is listed.
    """
    with _get_connection() as conn:
        if not _table_exists(conn, "moderators"):
            return False
        return conn.execute(
            "SELECT 1 FROM moderators WHERE discord_user_id = ?", (str(user_id),)
        ).fetchone() is not None


def get_player_record(target_id, limit: int = 10) -> dict:
    """A player's reports, blocks and past moderation actions, newest first.

    For the summary posted in the mod channel when a group chat opens.
    """
    target_id = str(target_id)
    record = {"reports": [], "blocks": [], "actions": [], "notes": [], "chats": [],
              "report_total": 0, "block_total": 0}
    with _get_connection() as conn:
        if _table_exists(conn, "player_reports"):
            record["report_total"] = conn.execute(
                "SELECT COUNT(*) FROM player_reports WHERE reported_id = ?", (target_id,)
            ).fetchone()[0]
            for row in conn.execute(
                "SELECT id, reporter_id, reporter_name, match_type, reasons, details, created_at "
                "FROM player_reports WHERE reported_id = ? ORDER BY id DESC LIMIT ?",
                (target_id, limit),
            ).fetchall():
                entry = dict(row)
                entry["reasons"] = _reasons(row["reasons"])
                record["reports"].append(entry)
        if _table_exists(conn, "blocked_users"):
            record["block_total"] = conn.execute(
                "SELECT COUNT(*) FROM blocked_users WHERE blocked_user_id = ?", (target_id,)
            ).fetchone()[0]
            record["blocks"] = [dict(r) for r in conn.execute(
                "SELECT user_id, reason, created_at FROM blocked_users "
                "WHERE blocked_user_id = ? ORDER BY created_at DESC LIMIT ?",
                (target_id, limit),
            ).fetchall()]
        if _table_exists(conn, "moderation_actions"):
            record["actions"] = [dict(r) for r in conn.execute(
                "SELECT action, duration_minutes, duration_label, reason, by_name, created_at "
                "FROM moderation_actions WHERE target_id = ? ORDER BY id DESC LIMIT ?",
                (target_id, limit),
            ).fetchall()]
        if _table_exists(conn, "moderation_notes"):
            record["notes"] = [dict(r) for r in conn.execute(
                "SELECT note, by_name, created_at FROM moderation_notes "
                "WHERE target_id = ? ORDER BY id DESC LIMIT ?",
                (target_id, limit),
            ).fetchall()]
        if _table_exists(conn, "moderation_group_chats"):
            record["chats"] = [dict(r) for r in conn.execute(
                "SELECT id, opened_by_name, created_at, closed_at, closed_by_name, message_count "
                "FROM moderation_group_chats WHERE target_id = ? AND closed_at IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (target_id, 5),
            ).fetchall()]
    return record


# ── mod notes ──


def add_moderation_note(target_id, note, by_id, by_name) -> int:
    with _get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO moderation_notes (target_id, note, by_id, by_name) VALUES (?, ?, ?, ?)",
            (str(target_id), note, str(by_id), by_name),
        )
        return cur.lastrowid


# ── repeat-offender flags ──


def count_recent_complaints(target_id, days: int) -> int:
    """Reports plus blocks against the player in the last ``days`` days."""
    target_id = str(target_id)
    since = f"-{int(days)} days"
    total = 0
    with _get_connection() as conn:
        if _table_exists(conn, "player_reports"):
            total += conn.execute(
                "SELECT COUNT(*) FROM player_reports WHERE reported_id = ? AND created_at >= datetime('now', ?)",
                (target_id, since),
            ).fetchone()[0]
        if _table_exists(conn, "blocked_users"):
            total += conn.execute(
                "SELECT COUNT(*) FROM blocked_users WHERE blocked_user_id = ? AND created_at >= datetime('now', ?)",
                (target_id, since),
            ).fetchone()[0]
    return total


def recently_flagged(target_id, days: int) -> bool:
    """Was a repeat-offender heads-up posted for this player in the last ``days`` days?"""
    with _get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM moderation_alerts WHERE kind = 'repeat' AND ref LIKE ? "
            "AND alerted_at >= datetime('now', ?)",
            (f"{target_id}|%", f"-{int(days)} days"),
        ).fetchone() is not None


def mark_flagged(target_id):
    with _get_connection() as conn:
        now = conn.execute("SELECT datetime('now')").fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES ('repeat', ?)",
            (f"{target_id}|{now}",),
        )


# ── weekly summary ──


def weekly_sent(ref: str) -> bool:
    with _get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM moderation_alerts WHERE kind = 'weekly' AND ref = ?", (ref,)
        ).fetchone() is not None


def mark_weekly_sent(ref: str):
    with _get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES ('weekly', ?)", (ref,))


def get_weekly_stats(days: int = 7) -> dict:
    """Counts for the weekly mod summary (last ``days`` days)."""
    since = f"-{int(days)} days"
    stats = {"reports": 0, "blocks": 0, "actions": [], "chats_opened": 0, "chats_closed": 0,
             "open_chats": [], "top_players": [], "flagged": 0}
    with _get_connection() as conn:
        if _table_exists(conn, "player_reports"):
            stats["reports"] = conn.execute(
                "SELECT COUNT(*) FROM player_reports WHERE created_at >= datetime('now', ?)", (since,)
            ).fetchone()[0]
        if _table_exists(conn, "blocked_users"):
            stats["blocks"] = conn.execute(
                "SELECT COUNT(*) FROM blocked_users WHERE created_at >= datetime('now', ?)", (since,)
            ).fetchone()[0]
        complaints = []
        if _table_exists(conn, "player_reports"):
            complaints.append(
                "SELECT reported_id AS target_id FROM player_reports WHERE created_at >= datetime('now', :since)"
            )
        if _table_exists(conn, "blocked_users"):
            complaints.append(
                "SELECT blocked_user_id AS target_id FROM blocked_users WHERE created_at >= datetime('now', :since)"
            )
        if complaints:
            stats["top_players"] = [dict(r) for r in conn.execute(
                "SELECT target_id, COUNT(*) AS n FROM (" + " UNION ALL ".join(complaints) + ") "
                "GROUP BY target_id ORDER BY n DESC LIMIT 5",
                {"since": since},
            ).fetchall()]
        stats["actions"] = [dict(r) for r in conn.execute(
            "SELECT action, COUNT(*) AS n FROM moderation_actions "
            "WHERE created_at >= datetime('now', ?) GROUP BY action ORDER BY n DESC",
            (since,),
        ).fetchall()]
        stats["chats_opened"] = conn.execute(
            "SELECT COUNT(*) FROM moderation_group_chats WHERE created_at >= datetime('now', ?)", (since,)
        ).fetchone()[0]
        stats["chats_closed"] = conn.execute(
            "SELECT COUNT(*) FROM moderation_group_chats WHERE closed_at >= datetime('now', ?)", (since,)
        ).fetchone()[0]
        stats["open_chats"] = [dict(r) for r in conn.execute(
            "SELECT target_id, channel_id, created_at FROM moderation_group_chats "
            "WHERE closed_at IS NULL ORDER BY id"
        ).fetchall()]
        stats["flagged"] = conn.execute(
            "SELECT COUNT(*) FROM moderation_alerts WHERE kind = 'repeat' AND alerted_at >= datetime('now', ?)",
            (since,),
        ).fetchone()[0]
    return stats


# ── website requests (summary posts, match flips) ──


def get_pending_summary_requests(limit: int = 10) -> list[dict]:
    with _get_connection() as conn:
        if not _table_exists(conn, "moderation_summary_requests"):
            return []
        return [dict(r) for r in conn.execute(
            "SELECT * FROM moderation_summary_requests WHERE done_at IS NULL ORDER BY id LIMIT ?", (limit,)
        ).fetchall()]


def mark_summary_done(request_id: int):
    with _get_connection() as conn:
        conn.execute(
            "UPDATE moderation_summary_requests SET done_at = datetime('now') WHERE id = ?", (int(request_id),)
        )


def get_pending_match_flips(limit: int = 25) -> list[dict]:
    """Pending flips, oldest match first (so each replay builds on the last)."""
    with _get_connection() as conn:
        if not _table_exists(conn, "moderation_match_flips"):
            return []
        return [dict(r) for r in conn.execute(
            "SELECT * FROM moderation_match_flips WHERE status = 'pending' ORDER BY match_id, id LIMIT ?",
            (limit,),
        ).fetchall()]


def finish_match_flip(flip_id: int, status: str, result: str):
    with _get_connection() as conn:
        conn.execute(
            "UPDATE moderation_match_flips SET status = ?, result = ?, done_at = datetime('now') WHERE id = ?",
            (status, result, int(flip_id)),
        )


# ── thanking reporters when a player is banned or pairing-blocked ──
# moderation_alerts rows: kind 'thanks' (report id thanked), 'thanks_action'
# (moderation_actions id handled), 'thanks_pban' (pairing_bans user|banned_at
# handled), 'thanks_seeded' (bans before this feature are skipped).


def _seed_thanks(conn):
    if conn.execute("SELECT 1 FROM moderation_alerts WHERE kind = 'thanks_seeded'").fetchone():
        return
    conn.execute(
        "INSERT OR IGNORE INTO moderation_alerts (kind, ref) "
        "SELECT 'thanks_action', CAST(id AS TEXT) FROM moderation_actions"
    )
    if _table_exists(conn, "pairing_bans"):
        conn.execute(
            "INSERT OR IGNORE INTO moderation_alerts (kind, ref) "
            "SELECT 'thanks_pban', user_id || '|' || banned_at FROM pairing_bans"
        )
    conn.execute("INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES ('thanks_seeded', '1')")


def get_new_ban_targets() -> list[tuple[str, str]]:
    """Players banned or pairing-blocked since last time: [(key, target_id)].

    Covers alert buttons, the website and ``!ban``. Bans from before this
    feature are skipped. Call ``mark_ban_handled(key)`` after each.
    """
    out = []
    with _get_connection() as conn:
        _seed_thanks(conn)
        for row in conn.execute(
            "SELECT id, target_id FROM moderation_actions a WHERE action IN ('ban', 'pairing_block') "
            "AND NOT EXISTS (SELECT 1 FROM moderation_alerts m WHERE m.kind = 'thanks_action' "
            "AND m.ref = CAST(a.id AS TEXT)) ORDER BY id"
        ).fetchall():
            out.append((f"thanks_action:{row['id']}", str(row["target_id"])))
        if _table_exists(conn, "pairing_bans"):
            for row in conn.execute(
                "SELECT user_id, banned_at FROM pairing_bans p WHERE NOT EXISTS (SELECT 1 FROM moderation_alerts m "
                "WHERE m.kind = 'thanks_pban' AND m.ref = p.user_id || '|' || p.banned_at)"
            ).fetchall():
                out.append((f"thanks_pban:{row['user_id']}|{row['banned_at']}", str(row["user_id"])))
    return out


def mark_ban_handled(key: str):
    kind, ref = key.split(":", 1)
    with _get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES (?, ?)", (kind, ref))


def get_unthanked_reports(target_id) -> list[dict]:
    """Reports against the player whose reporter hasn't been thanked yet."""
    with _get_connection() as conn:
        if not _table_exists(conn, "player_reports"):
            return []
        return [dict(r) for r in conn.execute(
            "SELECT id, reporter_id, reported_name FROM player_reports r WHERE reported_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM moderation_alerts m WHERE m.kind = 'thanks' "
            "AND m.ref = CAST(r.id AS TEXT)) ORDER BY id",
            (str(target_id),),
        ).fetchall()]


def mark_reports_thanked(report_ids):
    with _get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO moderation_alerts (kind, ref) VALUES ('thanks', ?)",
            [(str(i),) for i in report_ids],
        )
