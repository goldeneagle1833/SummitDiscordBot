"""Repository for Explorer Series host applications (explorer.db)."""

import logging
import sqlite3

import webapp_config

logger = logging.getLogger(__name__)

STATUSES = ("pending", "pre_approved", "approved", "rejected")

SCORE_FIELDS = ("enthusiasm", "track_record", "local_activity")

# Columns an applicant supplies. Kept in one place so the create path, the CSV
# export and the tests stay in step.
APPLICATION_FIELDS = (
    "discord_handle",
    "first_name",
    "last_name",
    "email",
    "city",
    "state",
    "country",
    "lgs_name",
    "lgs_url",
    "lgs_confirmed",
    "expected_attendance",
    "proposed_dates",
    "events_run",
    "events_run_count",
    "avg_headcount",
    "motivation",
    "read_navigator_role",
    "reference_contact",
    "anything_else",
    "referral",
)


class ExplorerApplicationRepository:
    """Data access for Explorer host applications, votes and comments."""

    def _conn(self):
        # Resolved per call so tests can repoint webapp_config at a temp DB.
        conn = sqlite3.connect(str(webapp_config.EXPLORER_DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ── Applications ─────────────────────────────────────────────────────────

    def create_application(
        self, discord_user_id: str | None, fields: dict, source: str = "application",
        created_by: str | None = None,
    ) -> int:
        """Insert an application and return its new id."""
        columns = ["discord_user_id", "source", "created_by"]
        values = [discord_user_id, source, created_by]
        for name in APPLICATION_FIELDS:
            if name in fields:
                columns.append(name)
                values.append(fields[name])

        placeholders = ", ".join("?" for _ in columns)
        with self._conn() as conn:
            cur = conn.execute(
                f"INSERT INTO explorer_applications ({', '.join(columns)})"
                f" VALUES ({placeholders})",
                values,
            )
            conn.commit()
            return cur.lastrowid

    def get_application(self, application_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM explorer_applications WHERE id = ?", (application_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_by_discord_user(self, discord_user_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM explorer_applications WHERE discord_user_id = ?",
                (str(discord_user_id),),
            ).fetchone()
            return dict(row) if row else None

    def list_applications(self, status: str | None = None) -> list[dict]:
        """List applications with their vote aggregate, newest first.

        Each row carries ``average_score`` (mean of every score a reviewer has
        given, across all three criteria) and ``vote_count``.
        """
        where = " WHERE a.status = ?" if status else ""
        params = (status,) if status else ()
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.*,
                       COUNT(DISTINCT v.id) AS vote_count,
                       AVG(v.enthusiasm) AS avg_enthusiasm,
                       AVG(v.track_record) AS avg_track_record,
                       AVG(v.local_activity) AS avg_local_activity,
                       (SELECT COUNT(*) FROM explorer_application_comments c
                         WHERE c.application_id = a.id) AS comment_count
                FROM explorer_applications a
                LEFT JOIN explorer_application_votes v ON v.application_id = a.id
                {where}
                GROUP BY a.id
                ORDER BY a.submitted_at DESC, a.id DESC
                """,
                params,
            ).fetchall()

        return [self._with_average(dict(row)) for row in rows]

    @staticmethod
    def _with_average(row: dict) -> dict:
        """Add an overall average across the three criteria.

        Criteria a reviewer left blank are skipped rather than counted as zero,
        so a half-filled scorecard doesn't drag the average down.
        """
        parts = [
            row.get(f"avg_{field}")
            for field in SCORE_FIELDS
            if row.get(f"avg_{field}") is not None
        ]
        row["average_score"] = round(sum(parts) / len(parts), 2) if parts else None
        return row

    def update_status(self, application_id: int, status: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE explorer_applications
                   SET status = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (status, application_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def set_coordinates(
        self, application_id: int, latitude: float | None, longitude: float | None
    ) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE explorer_applications
                   SET latitude = ?, longitude = ?, geocoded_at = datetime('now')
                   WHERE id = ?""",
                (latitude, longitude, application_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_application(self, application_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM explorer_applications WHERE id = ?", (application_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Votes ────────────────────────────────────────────────────────────────

    def upsert_vote(
        self, application_id: int, voter_user_id: str, voter_name: str | None, scores: dict
    ) -> None:
        """Record (or replace) one reviewer's scorecard for an application."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO explorer_application_votes (
                    application_id, voter_user_id, voter_name,
                    enthusiasm, track_record, local_activity, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT (application_id, voter_user_id) DO UPDATE SET
                    voter_name = excluded.voter_name,
                    enthusiasm = excluded.enthusiasm,
                    track_record = excluded.track_record,
                    local_activity = excluded.local_activity,
                    updated_at = excluded.updated_at
                """,
                (
                    application_id,
                    str(voter_user_id),
                    voter_name,
                    scores.get("enthusiasm"),
                    scores.get("track_record"),
                    scores.get("local_activity"),
                ),
            )
            conn.commit()

    def get_votes(self, application_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM explorer_application_votes
                   WHERE application_id = ?
                   ORDER BY updated_at DESC""",
                (application_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_vote(self, application_id: int, voter_user_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """DELETE FROM explorer_application_votes
                   WHERE application_id = ? AND voter_user_id = ?""",
                (application_id, str(voter_user_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Comments ─────────────────────────────────────────────────────────────

    def add_comment(
        self, application_id: int, author_user_id: str, author_name: str | None, body: str
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO explorer_application_comments
                   (application_id, author_user_id, author_name, body)
                   VALUES (?, ?, ?, ?)""",
                (application_id, str(author_user_id), author_name, body),
            )
            conn.commit()
            return cur.lastrowid

    def get_comments(self, application_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM explorer_application_comments
                   WHERE application_id = ?
                   ORDER BY created_at ASC, id ASC""",
                (application_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_comment(self, comment_id: int, author_user_id: str | None = None) -> bool:
        """Delete a comment. Scoped to the author unless author_user_id is None."""
        sql = "DELETE FROM explorer_application_comments WHERE id = ?"
        params: list = [comment_id]
        if author_user_id is not None:
            sql += " AND author_user_id = ?"
            params.append(str(author_user_id))
        with self._conn() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount > 0
