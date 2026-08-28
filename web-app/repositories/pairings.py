"""Read-only access to the bot's active pairing tables in match_records.db.

Used to decide whether an externally reported result (e.g. from Sorcery
Online) belongs to a Summit queue pairing and should therefore go through
the bot's normal match pipeline instead of the external_matches table.
"""

import sqlite3

import webapp_config


class PairingRepository:
    """Look up Summit pairings written by the Discord bot."""

    def __init__(self, db_path=None):
        self._db_path = str(db_path or webapp_config.MATCH_RECORDS_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _as_int(value) -> int | None:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def get_pairing_by_id(self, pairing_id, queue_type: str | None = None) -> dict | None:
        """Return a pairing (any status) by id, or None.

        Checks limited_active_pairings when queue_type is "limited",
        otherwise active_pairings.
        """
        pid = self._as_int(pairing_id)
        if pid is None:
            return None
        conn = self._get_connection()
        try:
            if queue_type == "limited":
                row = self._fetch_limited(conn, "pairing_id = ?", (pid,))
            else:
                row = self._fetch_ranked(conn, "pairing_id = ?", (pid,))
                if row is None and queue_type is None:
                    row = self._fetch_limited(conn, "pairing_id = ?", (pid,))
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        return row

    def find_active_pairing(self, player_a, player_b) -> dict | None:
        """Return the most recent *active* pairing between two players, or None."""
        a = self._as_int(player_a)
        b = self._as_int(player_b)
        if a is None or b is None or a == b:
            return None
        where = (
            "status = 'active' AND "
            "((player1_id = ? AND player2_id = ?) OR (player1_id = ? AND player2_id = ?))"
        )
        params = (a, b, b, a)
        conn = self._get_connection()
        candidates = []
        try:
            for fetch in (self._fetch_ranked, self._fetch_limited):
                try:
                    row = fetch(conn, where, params)
                except sqlite3.OperationalError:
                    # That pairing table doesn't exist yet on this install.
                    row = None
                if row is not None:
                    candidates.append(row)
        finally:
            conn.close()
        if not candidates:
            return None
        return max(candidates, key=lambda row: row.get("created_at") or "")

    def _fetch_ranked(self, conn, where: str, params) -> dict | None:
        try:
            row = conn.execute(
                f"""SELECT pairing_id, guild_id, player1_id, player2_id,
                           player1_deck_url, player2_deck_url, created_at, status,
                           COALESCE(match_type, 'ranked') AS match_type
                    FROM active_pairings
                    WHERE {where}
                    ORDER BY created_at DESC LIMIT 1""",
                params,
            ).fetchone()
        except sqlite3.OperationalError as exc:
            # Older schema without match_type
            if "match_type" not in str(exc):
                raise
            row = conn.execute(
                f"""SELECT pairing_id, guild_id, player1_id, player2_id,
                           player1_deck_url, player2_deck_url, created_at, status,
                           'ranked' AS match_type
                    FROM active_pairings
                    WHERE {where}
                    ORDER BY created_at DESC LIMIT 1""",
                params,
            ).fetchone()
        return dict(row) if row else None

    def _fetch_limited(self, conn, where: str, params) -> dict | None:
        row = conn.execute(
            f"""SELECT pairing_id, guild_id, player1_id, player2_id,
                       player1_deck_url, player2_deck_url, created_at, status,
                       'limited' AS match_type
                FROM limited_active_pairings
                WHERE {where}
                ORDER BY created_at DESC LIMIT 1""",
            params,
        ).fetchone()
        return dict(row) if row else None
