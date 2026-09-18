"""Data access for site-hosted brackets."""

import logging
import sqlite3
from datetime import datetime

import webapp_config

logger = logging.getLogger(__name__)


class BracketRepository:
    """Repository for brackets, bracket_entrants, bracket_matches, ticket_holders."""

    def __init__(self, db_path=None):
        self._explicit_path = db_path

    @property
    def _db_path(self) -> str:
        """Resolved late so test fixtures can repoint the database."""
        return str(self._explicit_path or webapp_config.MATCH_RECORDS_DB_PATH)

    def _get_connection(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_tables(self):
        from migrations.create_bracket_tables import create_bracket_tables

        create_bracket_tables(self._db_path)

    # -- Brackets -------------------------------------------------

    def create_bracket(self, data: dict) -> int:
        now = datetime.now().isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO brackets (
                slug, name, description, entrant_count, bracket_size, status,
                seeded_from, elo_event_name, confirm_hours, created_by,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)
            """,
            (
                data["slug"],
                data["name"],
                data.get("description"),
                data.get("entrant_count", 0),
                data.get("bracket_size", 0),
                data.get("seeded_from"),
                data.get("elo_event_name"),
                data.get("confirm_hours", 48),
                data.get("created_by"),
                now,
                now,
            ),
        )
        bracket_id = cur.lastrowid
        conn.commit()
        conn.close()
        return bracket_id

    EDITABLE_FIELDS = ("name", "description", "confirm_hours")

    def update_bracket(self, bracket_id: int, fields: dict) -> bool:
        updates = {k: v for k, v in fields.items() if k in self.EDITABLE_FIELDS}
        if not updates:
            return False
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE brackets SET {assignments}, updated_at = ? WHERE bracket_id = ?",
            (*updates.values(), datetime.now().isoformat(), bracket_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def set_status(self, bracket_id: int, status: str) -> bool:
        now = datetime.now().isoformat()
        column = {
            "published": "published_at",
            "complete": "completed_at",
        }.get(status)

        conn = self._get_connection()
        cur = conn.cursor()
        if column:
            cur.execute(
                f"UPDATE brackets SET status = ?, {column} = ?, updated_at = ? WHERE bracket_id = ?",
                (status, now, now, bracket_id),
            )
        else:
            cur.execute(
                "UPDATE brackets SET status = ?, updated_at = ? WHERE bracket_id = ?",
                (status, now, bracket_id),
            )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def set_counts(self, bracket_id: int, entrant_count: int, bracket_size: int):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE brackets SET entrant_count = ?, bracket_size = ?, updated_at = ?
            WHERE bracket_id = ?
            """,
            (entrant_count, bracket_size, datetime.now().isoformat(), bracket_id),
        )
        conn.commit()
        conn.close()

    def get_bracket(self, bracket_id=None, slug=None) -> dict | None:
        conn = self._get_connection()
        cur = conn.cursor()
        if slug is not None:
            cur.execute("SELECT * FROM brackets WHERE slug = ?", (slug,))
        else:
            cur.execute("SELECT * FROM brackets WHERE bracket_id = ?", (bracket_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_brackets(self, published_only: bool = True) -> list[dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        where = "WHERE status != 'draft'" if published_only else ""
        cur.execute(f"""
            SELECT * FROM brackets
            {where}
            ORDER BY COALESCE(published_at, created_at) DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_bracket(self, bracket_id: int) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM bracket_matches WHERE bracket_id = ?", (bracket_id,))
        cur.execute("DELETE FROM bracket_decks WHERE bracket_id = ?", (bracket_id,))
        cur.execute("DELETE FROM bracket_entrants WHERE bracket_id = ?", (bracket_id,))
        cur.execute("DELETE FROM brackets WHERE bracket_id = ?", (bracket_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    # -- Entrants -------------------------------------------------

    def replace_entrants(self, bracket_id: int, entrants: list[dict]):
        """Rewrite the seeded field. Seeds are assigned by list order."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM bracket_entrants WHERE bracket_id = ?", (bracket_id,))
        cur.executemany(
            """
            INSERT INTO bracket_entrants (
                bracket_id, seed, user_id, display_name, elo, games, is_ticket_holder
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    bracket_id,
                    index + 1,
                    entrant.get("user_id"),
                    entrant["display_name"],
                    entrant.get("elo"),
                    entrant.get("games"),
                    1 if entrant.get("is_ticket_holder") else 0,
                )
                for index, entrant in enumerate(entrants)
            ],
        )
        conn.commit()
        conn.close()

    def get_entrants(self, bracket_id: int) -> list[dict]:
        """Entrants in seed order, with their profile picture when we have one."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'"
        )
        has_profiles = cur.fetchone() is not None

        if has_profiles:
            # A player can have both a Discord and a Google profile; prefer Discord.
            cur.execute(
                """
                SELECT e.*,
                       (SELECT p.avatar FROM user_profiles p
                         WHERE p.user_id = e.user_id
                         ORDER BY CASE WHEN p.provider = 'discord' THEN 0 ELSE 1 END
                         LIMIT 1) AS avatar,
                       (SELECT p.provider FROM user_profiles p
                         WHERE p.user_id = e.user_id
                         ORDER BY CASE WHEN p.provider = 'discord' THEN 0 ELSE 1 END
                         LIMIT 1) AS provider
                FROM bracket_entrants e
                WHERE e.bracket_id = ?
                ORDER BY e.seed
                """,
                (bracket_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM bracket_entrants WHERE bracket_id = ? ORDER BY seed",
                (bracket_id,),
            )

        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # -- Decks ----------------------------------------------------

    def upsert_deck(self, bracket_id: int, seed: int, data: dict):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bracket_decks (
                bracket_id, seed, user_id, deck_url, deck_name,
                avatar_name, deck_json, submitted_by, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bracket_id, seed) DO UPDATE SET
                user_id = excluded.user_id,
                deck_url = excluded.deck_url,
                deck_name = excluded.deck_name,
                avatar_name = excluded.avatar_name,
                deck_json = excluded.deck_json,
                submitted_by = excluded.submitted_by,
                submitted_at = excluded.submitted_at
            """,
            (
                bracket_id,
                seed,
                data.get("user_id"),
                data.get("deck_url"),
                data.get("deck_name"),
                data.get("avatar_name"),
                data.get("deck_json"),
                data.get("submitted_by"),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    def get_decks(self, bracket_id: int) -> list[dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM bracket_decks WHERE bracket_id = ? ORDER BY seed",
            (bracket_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_deck(self, bracket_id: int, seed: int) -> dict | None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM bracket_decks WHERE bracket_id = ? AND seed = ?",
            (bracket_id, seed),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_deck(self, bracket_id: int, seed: int) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM bracket_decks WHERE bracket_id = ? AND seed = ?",
            (bracket_id, seed),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    # -- Matches --------------------------------------------------

    def replace_matches(self, bracket_id: int, matches: list[dict]):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM bracket_matches WHERE bracket_id = ?", (bracket_id,))
        cur.executemany(
            """
            INSERT INTO bracket_matches (
                bracket_id, match_no, round, round_title, position,
                next_match_no, next_slot,
                p1_seed, p1_user_id, p1_name,
                p2_seed, p2_user_id, p2_name,
                winner_user_id, winner_seed, state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    bracket_id,
                    m["match_no"],
                    m["round"],
                    m["round_title"],
                    m["position"],
                    m["next_match_no"],
                    m["next_slot"],
                    m["p1_seed"],
                    m["p1_user_id"],
                    m["p1_name"],
                    m["p2_seed"],
                    m["p2_user_id"],
                    m["p2_name"],
                    m["winner_user_id"],
                    m["winner_seed"],
                    m["state"],
                )
                for m in matches
            ],
        )
        conn.commit()
        conn.close()

    def get_matches(self, bracket_id: int) -> list[dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM bracket_matches
            WHERE bracket_id = ?
            ORDER BY round, position
            """,
            (bracket_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_match(self, bracket_id: int, match_no: int) -> dict | None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM bracket_matches WHERE bracket_id = ? AND match_no = ?",
            (bracket_id, match_no),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_match(self, bracket_id: int, match_no: int, fields: dict) -> bool:
        if not fields:
            return False
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE bracket_matches SET {assignments} WHERE bracket_id = ? AND match_no = ?",
            (*fields.values(), bracket_id, match_no),
        )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def get_expired_reports(self, now_ts: int) -> list[dict]:
        """Reported matches whose confirmation window has run out."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.* FROM bracket_matches m
            JOIN brackets b ON b.bracket_id = m.bracket_id
            WHERE m.state = 'reported'
              AND m.expires_at IS NOT NULL
              AND m.expires_at <= ?
              AND b.status = 'published'
            """,
            (now_ts,),
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_player_matches(self, user_id: str) -> list[dict]:
        """A player's bracket matches that still need something from them."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.*, b.slug, b.name AS bracket_name
            FROM bracket_matches m
            JOIN brackets b ON b.bracket_id = m.bracket_id
            WHERE b.status = 'published'
              AND m.state IN ('pending', 'reported')
              AND (m.p1_user_id = ? OR m.p2_user_id = ?)
            ORDER BY m.round, m.position
            """,
            (str(user_id), str(user_id)),
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # -- Ticket holders -------------------------------------------

    def replace_ticket_holders(self, holders: list[dict]):
        now = datetime.now().isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM ticket_holders")
        cur.executemany(
            "INSERT INTO ticket_holders (user_id, display_name, synced_at) VALUES (?, ?, ?)",
            [(str(h["user_id"]), h.get("display_name"), now) for h in holders],
        )
        conn.commit()
        conn.close()

    def get_ticket_holders(self) -> list[dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ticket_holders")
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
