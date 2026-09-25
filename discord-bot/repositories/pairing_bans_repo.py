"""Repository for pairing-service bans in match_records.db (Discord bot side).

A pairing ban blocks a player from every way into the pairing service:
the LFG queue buttons, the website queue, ``!challenge`` and ladder
challenges. Bans are timed (24/48/72 hours) or lifetime (no expiry).
"""

import datetime
import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"

# Modal dropdown choices: value -> (label, hours or None for lifetime)
BAN_DURATIONS = {
    "24h": ("24 hours", 24),
    "48h": ("48 hours", 48),
    "72h": ("72 hours", 72),
    "lifetime": ("Lifetime", None),
}


@contextmanager
def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_ts(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def create_pairing_bans_table():
    """Create the pairing_bans table if it doesn't exist."""
    with _get_connection() as conn:
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


def _row_to_ban(row) -> dict:
    return {
        "user_id": int(row[0]),
        "user_name": row[1],
        "banned_by_id": int(row[2]),
        "banned_by_name": row[3],
        "reason": row[4],
        "duration_label": row[5],
        "banned_at": _parse_ts(row[6]),
        "expires_at": _parse_ts(row[7]),
    }


_SELECT = (
    "SELECT user_id, user_name, banned_by_id, banned_by_name, reason, "
    "duration_label, banned_at, expires_at FROM pairing_bans"
)


def set_pairing_ban(
    user_id: int | str,
    banned_by_id: int | str,
    reason: str,
    duration_key: str,
    user_name: str | None = None,
    banned_by_name: str | None = None,
) -> dict:
    """Create or replace a pairing ban. Returns the stored ban.

    ``duration_key`` is one of the keys in ``BAN_DURATIONS``.
    """
    if duration_key not in BAN_DURATIONS:
        raise ValueError(f"Unknown ban duration: {duration_key}")
    label, hours = BAN_DURATIONS[duration_key]
    now = _utcnow()
    expires_at = now + datetime.timedelta(hours=hours) if hours else None
    with _get_connection() as conn:
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
            (
                str(user_id),
                user_name,
                str(banned_by_id),
                banned_by_name,
                reason,
                label,
                now.isoformat(),
                expires_at.isoformat() if expires_at else None,
            ),
        )
    return {
        "user_id": int(user_id),
        "user_name": user_name,
        "banned_by_id": int(banned_by_id),
        "banned_by_name": banned_by_name,
        "reason": reason,
        "duration_label": label,
        "banned_at": now,
        "expires_at": expires_at,
    }


def get_pairing_ban(user_id: int | str) -> dict | None:
    """Return the active ban for a user, or None. Expired bans are deleted."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(_SELECT + " WHERE user_id = ?", (str(user_id),))
        row = cur.fetchone()
        if not row:
            return None
        ban = _row_to_ban(row)
        if ban["expires_at"] and ban["expires_at"] <= _utcnow():
            cur.execute("DELETE FROM pairing_bans WHERE user_id = ?", (str(user_id),))
            return None
        return ban


def is_pairing_banned(user_id: int | str) -> bool:
    """True if the user currently has an active pairing ban."""
    try:
        return get_pairing_ban(user_id) is not None
    except sqlite3.Error as e:
        # Never let a DB hiccup take the whole pairing service down.
        logger.error(f"pairing ban lookup failed for {user_id}: {e}")
        return False


def remove_pairing_ban(user_id: int | str) -> dict | None:
    """Delete a user's ban. Returns the removed ban, or None if there wasn't one."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(_SELECT + " WHERE user_id = ?", (str(user_id),))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("DELETE FROM pairing_bans WHERE user_id = ?", (str(user_id),))
        return _row_to_ban(row)


def get_active_pairing_bans() -> list[dict]:
    """All active bans, soonest to expire first, lifetime bans last."""
    now = _utcnow()
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(_SELECT)
        bans = [_row_to_ban(row) for row in cur.fetchall()]
        expired = [b for b in bans if b["expires_at"] and b["expires_at"] <= now]
        for ban in expired:
            cur.execute("DELETE FROM pairing_bans WHERE user_id = ?", (str(ban["user_id"]),))
    active = [b for b in bans if not (b["expires_at"] and b["expires_at"] <= now)]
    active.sort(key=lambda b: (b["expires_at"] is None, b["expires_at"] or now))
    return active


def format_time_remaining(ban: dict) -> str:
    """Human-readable time left on a ban, e.g. '1 day, 3 hours' or 'permanent'."""
    expires_at = ban.get("expires_at")
    if not expires_at:
        return "permanent"
    seconds = int((expires_at - _utcnow()).total_seconds())
    if seconds <= 0:
        return "expired"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if not days and minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts.append("less than a minute")
    return ", ".join(parts)


def pairing_ban_message(ban: dict) -> str:
    """The message shown to a banned player when they try to use the pairing service."""
    reason = ban.get("reason") or "No reason given."
    if ban.get("expires_at"):
        unix = int(ban["expires_at"].timestamp())
        when = (
            f"**Time remaining:** {format_time_remaining(ban)} "
            f"(lifts <t:{unix}:R>, on <t:{unix}:f>)"
        )
    else:
        when = "**Duration:** Lifetime. This block does not expire."
    return (
        "🚫 You are currently blocked from the Summit pairing service.\n"
        f"**Reason:** {reason}\n"
        f"{when}\n"
        "If you think this is a mistake, please contact a server admin."
    )
