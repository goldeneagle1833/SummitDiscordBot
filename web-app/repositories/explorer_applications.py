"""Repository for Explorer Series host applications (explorer.db)."""

import logging
import sqlite3

import webapp_config

logger = logging.getLogger(__name__)

STATUSES = ("pending", "pre_approved", "approved", "rejected")

# The statuses an applicant can be told about. The rest are Council-internal.
DECIDED_STATUSES = ("approved", "rejected")

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
    "proposed_dates_notes",
    "events_run",
    "events_run_count",
    "avg_headcount",
    "motivation",
    "read_navigator_role",
    "reference_contact",
    "anything_else",
    "referral",
)


def normalize_handle(handle: str | None) -> str:
    """Lowercase a Discord handle and drop a leading @ so typed handles compare."""
    return (handle or "").strip().lstrip("@").strip().lower()


# Date rows a Council member should look at: anything vaguer than an exact
# date the applicant picked or wrote out in full.
CHECK_CONFIDENCE = ("low", "none")


def dates_need_check(application: dict, dates: list[dict]) -> bool:
    """True when an application's dates still want a person's eye.

    That's a free-text answer the parser couldn't read, or any vague row
    (a month, "mid-June", a season) nobody has confirmed yet.
    """
    if any(d.get("confirmed_at") or d.get("source") == "admin" for d in dates):
        return False
    if not dates:
        text = (application.get("proposed_dates") or application.get("proposed_dates_notes") or "")
        return bool(text.strip())
    return any(d.get("confidence") in CHECK_CONFIDENCE for d in dates)


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
        """The user's most recent application, if any."""
        applications = self.list_by_discord_user(discord_user_id)
        return applications[0] if applications else None

    def list_by_discord_user(self, discord_user_id: str) -> list[dict]:
        """Every application a user has made, newest first.

        One person may apply more than once, e.g. to host at several stores.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM explorer_applications
                   WHERE discord_user_id = ?
                   ORDER BY id DESC""",
                (str(discord_user_id),),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_by_handle(self, discord_handle: str | None) -> dict | None:
        """Find an application by Discord handle, ignoring case and a leading @."""
        handle = normalize_handle(discord_handle)
        if not handle:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM explorer_applications
                   WHERE LOWER(LTRIM(TRIM(discord_handle), '@')) = ?
                   ORDER BY submitted_at ASC, id ASC
                   LIMIT 1""",
                (handle,),
            ).fetchone()
            return dict(row) if row else None

    def claim_candidate(self, discord_user_id: str, discord_handle: str | None) -> dict | None:
        """Tie an admin-added candidate row to the Discord account it was meant for.

        Admins add candidates by handle before the person has logged in, so
        those rows have no discord_user_id. When someone whose Discord username
        matches logs in, hand them that row instead of letting them create a
        second one. Returns the claimed row, or None if nothing matched.
        """
        handle = normalize_handle(discord_handle)
        if not handle:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM explorer_applications
                   WHERE discord_user_id IS NULL
                     AND LOWER(LTRIM(TRIM(discord_handle), '@')) = ?
                   ORDER BY submitted_at ASC, id ASC
                   LIMIT 1""",
                (handle,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """UPDATE explorer_applications
                   SET discord_user_id = ?, updated_at = datetime('now')
                   WHERE id = ? AND discord_user_id IS NULL""",
                (str(discord_user_id), row["id"]),
            )
            conn.commit()
            return self.get_application(row["id"])

    def list_applications(
        self, status: str | None = None, voter_user_id: str | None = None
    ) -> list[dict]:
        """List applications with their vote aggregate, newest first.

        Each row carries ``average_score`` (mean of every score a reviewer has
        given, across all three criteria) and ``vote_count``. When
        ``voter_user_id`` is given, each row also carries ``my_vote`` (1 if
        that reviewer has voted on it, else 0).
        """
        where = " WHERE a.status = ?" if status else ""
        params = (str(voter_user_id or ""),) + ((status,) if status else ())
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.*,
                       COUNT(DISTINCT v.id) AS vote_count,
                       AVG(v.enthusiasm) AS avg_enthusiasm,
                       AVG(v.track_record) AS avg_track_record,
                       AVG(v.local_activity) AS avg_local_activity,
                       (SELECT COUNT(*) FROM explorer_application_comments c
                         WHERE c.application_id = a.id) AS comment_count,
                       EXISTS (SELECT 1 FROM explorer_application_votes mv
                                WHERE mv.application_id = a.id
                                  AND mv.voter_user_id = ?) AS my_vote
                FROM explorer_applications a
                LEFT JOIN explorer_application_votes v ON v.application_id = a.id
                {where}
                GROUP BY a.id
                ORDER BY a.submitted_at DESC, a.id DESC
                """,
                params,
            ).fetchall()

        applications = [self._with_average(dict(row)) for row in rows]
        dates = self.dates_by_application()
        for application in applications:
            application["dates"] = dates.get(application["id"], [])
            application["dates_need_check"] = dates_need_check(
                application, application["dates"]
            )
        return applications

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

    def list_unpublished(self) -> list[dict]:
        """Applications whose published decision is out of step with status.

        That is a decision nobody has been told about yet, or a published
        decision the Council has since taken back to pending/pre-approved.
        """
        placeholders = ", ".join("?" for _ in DECIDED_STATUSES)
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT * FROM explorer_applications
                    WHERE (status IN ({placeholders})
                           AND COALESCE(published_status, '') != status)
                       OR (status NOT IN ({placeholders})
                           AND published_status IS NOT NULL)
                    ORDER BY id""",
                (*DECIDED_STATUSES, *DECIDED_STATUSES),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_published(self, application_id: int, status: str | None) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE explorer_applications
                   SET published_status = ?, published_at = datetime('now')
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

    def update_application(self, application_id: int, fields: dict) -> bool:
        """Update an applicant's own answers. Ignores anything not an
        applicant-supplied field, so status and provenance can't be edited."""
        updates = [name for name in APPLICATION_FIELDS if name in fields]
        if not updates:
            return False

        assignments = ", ".join(f"{name} = ?" for name in updates)
        values = [fields[name] for name in updates]
        with self._conn() as conn:
            cur = conn.execute(
                f"""UPDATE explorer_applications
                    SET {assignments}, updated_at = datetime('now')
                    WHERE id = ?""",
                [*values, application_id],
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Preferred event dates ────────────────────────────────────────────────

    def get_dates(self, application_id: int) -> list[dict]:
        """An application's structured date rows, in the applicant's order."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM explorer_application_dates
                   WHERE application_id = ?
                   ORDER BY choice_rank ASC, id ASC""",
                (application_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def dates_locked(self, application_id: int) -> bool:
        """True once a Council member has confirmed or fixed these dates.

        Locked dates are never replaced by re-parsing the applicant's text.
        """
        with self._conn() as conn:
            row = conn.execute(
                """SELECT 1 FROM explorer_application_dates
                   WHERE application_id = ?
                     AND (source = 'admin' OR confirmed_at IS NOT NULL)
                   LIMIT 1""",
                (application_id,),
            ).fetchone()
        return row is not None

    def replace_dates(self, application_id: int, rows: list[dict], source: str) -> None:
        """Swap an application's date rows for new ones.

        rows are dicts with start, end, precision, confidence and raw, as
        produced by services.explorer_dates.
        """
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM explorer_application_dates WHERE application_id = ?",
                (application_id,),
            )
            conn.executemany(
                """INSERT INTO explorer_application_dates
                   (application_id, choice_rank, start_date, end_date,
                    precision, confidence, raw_text, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (application_id, rank, row.get("start"), row.get("end"),
                     row["precision"], row["confidence"], row.get("raw"), source)
                    for rank, row in enumerate(rows, start=1)
                ],
            )
            conn.commit()

    def application_ids_without_dates(self) -> list[int]:
        """Applications with no date rows yet (e.g. made before the table existed)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT a.id FROM explorer_applications a
                   WHERE NOT EXISTS (
                       SELECT 1 FROM explorer_application_dates d
                       WHERE d.application_id = a.id
                   )
                   ORDER BY a.id"""
            ).fetchall()
        return [r["id"] for r in rows]

    def dates_by_application(self) -> dict[int, list[dict]]:
        """Every application's date rows, keyed by application id."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM explorer_application_dates
                   ORDER BY application_id, choice_rank, id"""
            ).fetchall()
        grouped: dict[int, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["application_id"], []).append(dict(row))
        return grouped

    def confirm_dates(self, application_id: int, confirmed_by: str) -> int:
        """Mark an application's date rows as checked by a Council member."""
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE explorer_application_dates
                   SET confirmed_by = ?, confirmed_at = datetime('now')
                   WHERE application_id = ?""",
                (confirmed_by, application_id),
            )
            conn.commit()
            return cur.rowcount

    def set_admin_dates(self, application_id: int, rows: list[dict], admin_name: str) -> None:
        """Replace the dates with ones a Council member entered; they're locked from re-parsing."""
        self.replace_dates(application_id, rows, source="admin")
        if rows:
            self.confirm_dates(application_id, admin_name)
