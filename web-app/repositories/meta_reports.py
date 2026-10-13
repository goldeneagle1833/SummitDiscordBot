"""Meta Report storage: published reports, email subscribers and the email outbox.

Lives in its own database (META_REPORTS_DB_PATH) so subscriber emails stay out
of the analytics and match databases. Tables are created on first use.
"""

import json
import logging
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from webapp_config import META_REPORTS_DB_PATH

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class MetaReportRepository:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or META_REPORTS_DB_PATH)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS meta_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,          -- covered period, e.g. 2026-09-a
                    period_from TEXT NOT NULL,          -- YYYY-MM-DD, inclusive
                    period_through TEXT NOT NULL,       -- YYYY-MM-DD, inclusive
                    status TEXT NOT NULL DEFAULT 'draft',  -- draft | published
                    payload TEXT NOT NULL,              -- the report's numbers (JSON)
                    story TEXT NOT NULL DEFAULT '[]',   -- takeaways (JSON), editable by admins
                    built_at TEXT NOT NULL,
                    published_at TEXT,
                    published_by TEXT,
                    announce INTEGER NOT NULL DEFAULT 1,  -- 0 = publish quietly (back-filled reports)
                    discord_posted_at TEXT,
                    banner_created_at TEXT,
                    emails_queued_at TEXT
                );
                CREATE TABLE IF NOT EXISTS meta_report_subscribers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    token TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    unsubscribed_at TEXT,
                    confirm_sent_at TEXT
                );
                CREATE TABLE IF NOT EXISTS meta_report_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER NOT NULL,
                    subscriber_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed | skipped
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    UNIQUE (report_id, subscriber_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meta_report_emails_status
                    ON meta_report_emails (status);
            """)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(meta_reports)")}
            if "notes" not in cols:
                # Admin rewrites of auto text (counter pick "why" lines), kept across rebuilds.
                conn.execute("ALTER TABLE meta_reports ADD COLUMN notes TEXT NOT NULL DEFAULT '{}'")

    # ------------------------------------------------------------------ #
    # Reports                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _report(row: sqlite3.Row | None, with_payload: bool = True) -> dict | None:
        if row is None:
            return None
        report = {
            "id": row["id"],
            "slug": row["slug"],
            "from": row["period_from"],
            "through": row["period_through"],
            "status": row["status"],
            "story": json.loads(row["story"] or "[]"),
            "notes": json.loads(row["notes"] or "{}") if "notes" in row.keys() else {},
            "builtAt": row["built_at"],
            "publishedAt": row["published_at"],
            "publishedBy": row["published_by"],
            "announce": bool(row["announce"]),
            "discordPostedAt": row["discord_posted_at"],
            "bannerCreatedAt": row["banner_created_at"],
            "emailsQueuedAt": row["emails_queued_at"],
        }
        if with_payload:
            report["payload"] = json.loads(row["payload"] or "{}")
        return report

    def save_build(self, slug: str, period_from: str, period_through: str,
                   payload: dict, story: list) -> dict:
        """Insert a new draft, or refresh the numbers of an existing report.

        A rebuild keeps the report's status and its edited story; the
        auto-drafted story is only used when the report has none yet.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT story FROM meta_reports WHERE slug = ?", (slug,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """INSERT INTO meta_reports
                       (slug, period_from, period_through, payload, story, built_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (slug, period_from, period_through, json.dumps(payload), json.dumps(story), _now()),
                )
            else:
                keep_story = json.loads(existing["story"] or "[]") or story
                conn.execute(
                    "UPDATE meta_reports SET payload = ?, story = ?, built_at = ? WHERE slug = ?",
                    (json.dumps(payload), json.dumps(keep_story), _now(), slug),
                )
        return self.get(slug)

    def get(self, slug: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM meta_reports WHERE slug = ?", (slug,)).fetchone()
        return self._report(row)

    def list_reports(self, published_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM meta_reports"
        if published_only:
            sql += " WHERE status = 'published'"
        sql += " ORDER BY period_from DESC"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._report(r, with_payload=False) for r in rows]

    def reports_before(self, period_from: str, limit: int = 6) -> list[dict]:
        """Built reports (published or draft) for earlier periods, newest first, with payloads."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM meta_reports WHERE period_from < ?
                   ORDER BY period_from DESC LIMIT ?""",
                (period_from, limit),
            ).fetchall()
        return [self._report(r) for r in rows]

    def update_notes(self, slug: str, notes: dict) -> dict | None:
        with self._connect() as conn:
            conn.execute("UPDATE meta_reports SET notes = ? WHERE slug = ?", (json.dumps(notes), slug))
        return self.get(slug)

    def update_story(self, slug: str, story: list) -> dict | None:
        with self._connect() as conn:
            conn.execute("UPDATE meta_reports SET story = ? WHERE slug = ?", (json.dumps(story), slug))
        return self.get(slug)

    def publish(self, slug: str, published_by: str, announce: bool) -> dict | None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE meta_reports
                   SET status = 'published', published_at = COALESCE(published_at, ?),
                       published_by = COALESCE(published_by, ?), announce = ?
                   WHERE slug = ?""",
                (_now(), published_by, 1 if announce else 0, slug),
            )
        return self.get(slug)

    def unpublish(self, slug: str) -> dict | None:
        with self._connect() as conn:
            conn.execute("UPDATE meta_reports SET status = 'draft' WHERE slug = ?", (slug,))
        return self.get(slug)

    def delete_draft(self, slug: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM meta_reports WHERE slug = ? AND status = 'draft'", (slug,))
        return cur.rowcount > 0

    def mark_delivery(self, slug: str, column: str) -> None:
        if column not in ("discord_posted_at", "banner_created_at", "emails_queued_at"):
            raise ValueError(column)
        with self._connect() as conn:
            conn.execute(f"UPDATE meta_reports SET {column} = ? WHERE slug = ?", (_now(), slug))

    def undelivered(self) -> list[dict]:
        """Published, announced reports with an announcement still to send."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM meta_reports
                   WHERE status = 'published' AND announce = 1
                     AND (discord_posted_at IS NULL OR banner_created_at IS NULL
                          OR emails_queued_at IS NULL)
                   ORDER BY period_from""",
            ).fetchall()
        return [self._report(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Subscribers                                                          #
    # ------------------------------------------------------------------ #

    def add_subscriber(self, email: str) -> dict:
        """Add or re-activate an address. Returns the row; it needs confirming
        unless it was already confirmed and still subscribed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meta_report_subscribers WHERE email = ?", (email,)
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO meta_report_subscribers (email, token, created_at)
                       VALUES (?, ?, ?)""",
                    (email, secrets.token_urlsafe(24), _now()),
                )
            elif row["unsubscribed_at"]:
                # Coming back after unsubscribing means confirming again.
                conn.execute(
                    """UPDATE meta_report_subscribers
                       SET unsubscribed_at = NULL, confirmed_at = NULL, token = ?
                       WHERE id = ?""",
                    (secrets.token_urlsafe(24), row["id"]),
                )
            row = conn.execute(
                "SELECT * FROM meta_report_subscribers WHERE email = ?", (email,)
            ).fetchone()
        return dict(row)

    def mark_confirm_sent(self, subscriber_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE meta_report_subscribers SET confirm_sent_at = ? WHERE id = ?",
                (_now(), subscriber_id),
            )

    def confirm(self, token: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meta_report_subscribers WHERE token = ?", (token,)
            ).fetchone()
            if row is None:
                return None
            if not row["confirmed_at"] or row["unsubscribed_at"]:
                conn.execute(
                    """UPDATE meta_report_subscribers
                       SET confirmed_at = ?, unsubscribed_at = NULL WHERE id = ?""",
                    (_now(), row["id"]),
                )
            row = conn.execute(
                "SELECT * FROM meta_report_subscribers WHERE id = ?", (row["id"],)
            ).fetchone()
        return dict(row)

    def unsubscribe(self, token: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meta_report_subscribers WHERE token = ?", (token,)
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE meta_report_subscribers SET unsubscribed_at = COALESCE(unsubscribed_at, ?) WHERE id = ?",
                (_now(), row["id"]),
            )
            # Anything still queued for them is dropped.
            conn.execute(
                "UPDATE meta_report_emails SET status = 'skipped' WHERE subscriber_id = ? AND status = 'pending'",
                (row["id"],),
            )
            row = conn.execute(
                "SELECT * FROM meta_report_subscribers WHERE id = ?", (row["id"],)
            ).fetchone()
        return dict(row)

    def subscriber_counts(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT
                     SUM(CASE WHEN confirmed_at IS NOT NULL AND unsubscribed_at IS NULL THEN 1 ELSE 0 END) AS active,
                     SUM(CASE WHEN confirmed_at IS NULL AND unsubscribed_at IS NULL THEN 1 ELSE 0 END) AS unconfirmed,
                     SUM(CASE WHEN unsubscribed_at IS NOT NULL THEN 1 ELSE 0 END) AS unsubscribed
                   FROM meta_report_subscribers"""
            ).fetchone()
        return {k: int(row[k] or 0) for k in ("active", "unconfirmed", "unsubscribed")}

    # ------------------------------------------------------------------ #
    # Email outbox                                                         #
    # ------------------------------------------------------------------ #

    def queue_report_emails(self, report_id: int) -> int:
        """One row per active subscriber; re-queuing the same report adds nobody twice."""
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO meta_report_emails (report_id, subscriber_id, created_at)
                   SELECT ?, id, ? FROM meta_report_subscribers
                   WHERE confirmed_at IS NOT NULL AND unsubscribed_at IS NULL""",
                (report_id, _now()),
            )
        return cur.rowcount

    def pending_emails(self, limit: int = 50, max_attempts: int = 5) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT e.id, e.report_id, e.attempts, s.email, s.token, r.slug
                   FROM meta_report_emails e
                   JOIN meta_report_subscribers s ON s.id = e.subscriber_id
                   JOIN meta_reports r ON r.id = e.report_id
                   WHERE e.status = 'pending' AND e.attempts < ?
                     AND s.unsubscribed_at IS NULL AND r.status = 'published'
                   ORDER BY e.id LIMIT ?""",
                (max_attempts, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_email(self, email_id: int, success: bool, error: str | None = None,
                   max_attempts: int = 5) -> None:
        with self._connect() as conn:
            if success:
                conn.execute(
                    "UPDATE meta_report_emails SET status = 'sent', sent_at = ?, attempts = attempts + 1 WHERE id = ?",
                    (_now(), email_id),
                )
            else:
                conn.execute(
                    """UPDATE meta_report_emails
                       SET attempts = attempts + 1, last_error = ?,
                           status = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE 'pending' END
                       WHERE id = ?""",
                    ((error or "")[:500], max_attempts, email_id),
                )

    def email_counts(self, report_id: int) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM meta_report_emails WHERE report_id = ? GROUP BY status",
                (report_id,),
            ).fetchall()
        return {r["status"]: r["n"] for r in rows}
