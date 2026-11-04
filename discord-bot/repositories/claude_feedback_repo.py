"""Feedback requests that Claude turns into pull requests (Discord bot side).

One row per message posted in the feedback channel. The row follows the
request from triage, to a GitHub issue, to the pull request Claude opens,
to merged or closed.

Statuses:
    skipped            Claude decided it's not something to change (chatter, thanks...)
    awaiting_approval  Actionable, but Claude wants the owner to OK it first
    dismissed          The owner dismissed it
    issue_open         GitHub issue filed; waiting for Claude's PR
    pr_open            PR is open; owner has been DMed
    merged / closed    PR finished
    no_pr              Claude didn't open a PR in time (or chose not to)
    failed             Something broke (see error)
"""

import datetime
import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"

OPEN_STATUSES = ("issue_open", "pr_open")


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


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_claude_feedback_table():
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claude_feedback_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE NOT NULL,
                channel_id TEXT NOT NULL,
                guild_id TEXT,
                author_id TEXT NOT NULL,
                author_name TEXT,
                content TEXT NOT NULL,
                attachments TEXT,
                jump_url TEXT,
                kind TEXT,
                title TEXT,
                summary TEXT,
                details TEXT,
                likely_area TEXT,
                risk TEXT,
                triage_reason TEXT,
                status TEXT NOT NULL,
                issue_number INTEGER,
                pr_number INTEGER,
                pr_url TEXT,
                head_sha TEXT,
                dm_channel_id TEXT,
                dm_message_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cfr_status ON claude_feedback_requests(status)"
        )


def create_request(*, message_id, channel_id, guild_id, author_id, author_name,
                   content, attachments, jump_url, status="triaging") -> int | None:
    """Insert a new request. Returns None if this message was already recorded."""
    now = _now()
    with _get_connection() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO claude_feedback_requests
                   (message_id, channel_id, guild_id, author_id, author_name, content,
                    attachments, jump_url, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(message_id), str(channel_id), str(guild_id or ""), str(author_id),
                 author_name, content, attachments, jump_url, status, now, now),
            )
        except sqlite3.IntegrityError:
            return None
        return cur.lastrowid


_UPDATABLE = {
    "kind", "title", "summary", "details", "likely_area", "risk", "triage_reason",
    "status", "issue_number", "pr_number", "pr_url", "head_sha",
    "dm_channel_id", "dm_message_id", "error",
}


def update_request(request_id: int, **fields):
    bad = set(fields) - _UPDATABLE
    if bad:
        raise ValueError(f"Unknown fields: {bad}")
    if not fields:
        return
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _get_connection() as conn:
        conn.execute(
            f"UPDATE claude_feedback_requests SET {cols} WHERE id = ?",
            (*fields.values(), request_id),
        )


def get_request(request_id: int) -> dict | None:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM claude_feedback_requests WHERE id = ?", (request_id,)
        ).fetchone()
    return dict(row) if row else None


def get_open_requests() -> list[dict]:
    with _get_connection() as conn:
        rows = conn.execute(
            f"""SELECT * FROM claude_feedback_requests
                WHERE status IN ({",".join("?" * len(OPEN_STATUSES))})
                ORDER BY id""",
            OPEN_STATUSES,
        ).fetchall()
    return [dict(r) for r in rows]


def count_recent_by_author(author_id, hours: int = 24) -> int:
    """How many requests (that weren't skipped) this user made in the last N hours."""
    since = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    ).isoformat()
    with _get_connection() as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM claude_feedback_requests
               WHERE author_id = ? AND created_at >= ? AND status != 'skipped'""",
            (str(author_id), since),
        ).fetchone()
    return int(row[0])
