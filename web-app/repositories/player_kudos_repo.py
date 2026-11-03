"""Repository for player kudos (positive player reports) in match_records.db.

Kudos are the friendly opposite of a Report Player report: after a game a
player can thank their opponent and say why. They come from the Discord
bot's **Give Kudos** button on a match message, or from a partner (Play
Sorcery Online) through the partner API with ``source`` set.

Every kudos is tied to one recorded match between the two players
(``match_id`` in ``match_records``), and a player can give one kudos per
match. Unlike reports, kudos are public: the homepage Player of the Day
shows one, with the reason and (unless they chose otherwise) who gave it.

The table shape is shared with discord-bot/repositories/player_kudos_repo.py.
"""

import json
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


# (value, label). Same list as discord-bot/cogs/lfg/player_kudos.py KUDOS_REASONS.
KUDOS_REASONS = [
    ("good_sport", "Good sport, win or lose"),
    ("friendly", "Friendly and fun to play with"),
    ("great_voice", "Great to talk with on voice"),
    ("helpful", "Helped me learn or explained a rule"),
    ("good_pace", "Played at a good pace"),
    ("fair_play", "Honest and fair, reported the result right"),
    ("great_game", "Great game, well played"),
]
KUDOS_REASON_VALUES = [value for value, _ in KUDOS_REASONS]
KUDOS_REASON_LABELS = dict(KUDOS_REASONS)

# A match older than this can no longer get kudos.
KUDOS_WINDOW_DAYS = 14
# Player of the Day picks from kudos received in this many days before today.
POTD_LOOKBACK_DAYS = 7

CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS player_kudos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        giver_id TEXT NOT NULL,
        giver_name TEXT,
        receiver_id TEXT NOT NULL,
        receiver_name TEXT,
        match_id INTEGER NOT NULL,
        pairing_id INTEGER,
        match_type TEXT,
        reasons TEXT NOT NULL DEFAULT '[]',
        message TEXT,
        anonymous INTEGER NOT NULL DEFAULT 0,
        source TEXT,
        hidden INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
"""
CREATE_INDEXES_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_player_kudos_giver_match ON player_kudos (giver_id, match_id)",
    "CREATE INDEX IF NOT EXISTS idx_player_kudos_receiver ON player_kudos (receiver_id, created_at)",
]


class KudosError(Exception):
    """A kudos that can't be given; ``code`` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def reason_labels(values) -> list[str]:
    return [KUDOS_REASON_LABELS[v] for v in values if v in KUDOS_REASON_LABELS]


class PlayerKudosRepository:
    """Data access for the player_kudos table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        try:
            conn.execute(CREATE_TABLE_SQL)
            for sql in CREATE_INDEXES_SQL:
                conn.execute(sql)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _reasons(raw) -> list[str]:
        try:
            value = json.loads(raw or "[]")
        except (TypeError, ValueError):
            return []
        return [str(v) for v in value] if isinstance(value, list) else []

    # ── Finding the match ─────────────────────────────────────

    def find_kudos_match(self, giver_id: str, receiver_id: str, pairing_id: int | None = None) -> dict | None:
        """Return the recorded match the giver can give kudos for, or None.

        The match must be between exactly these two players, recorded in the
        last KUDOS_WINDOW_DAYS days, and not already have kudos from this
        giver. When ``pairing_id`` is given only that pairing's match counts.
        Newest match first.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
            if not cols:
                return None
            has_pairing = "pairing_id" in cols
            since = (datetime.now(timezone.utc) - timedelta(days=KUDOS_WINDOW_DAYS)).strftime("%Y-%m-%d")
            pairing_col = "m.pairing_id" if has_pairing else "NULL"
            # Production's match_records has no match_id column (it predates it);
            # the match ID is SQLite's rowid, as everywhere else in the code.
            sql = f"""
                SELECT m.rowid AS match_id, {pairing_col} AS pairing_id, m.match_type, m.timestamp
                FROM match_records m
                WHERE ((CAST(m.winner_id AS TEXT) = ? AND CAST(m.losser_id AS TEXT) = ?)
                    OR (CAST(m.winner_id AS TEXT) = ? AND CAST(m.losser_id AS TEXT) = ?))
                  AND m.timestamp >= ?
                  AND NOT EXISTS (
                      SELECT 1 FROM player_kudos k
                      WHERE k.giver_id = ? AND k.match_id = m.rowid
                  )
            """
            params = [giver_id, receiver_id, receiver_id, giver_id, since, giver_id]
            if pairing_id:
                if not has_pairing:
                    return None
                sql += " AND m.pairing_id = ?"
                params.append(int(pairing_id))
            sql += " ORDER BY m.timestamp DESC LIMIT 1"
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def has_recent_match(self, giver_id: str, receiver_id: str, pairing_id: int | None = None) -> bool:
        """True if the two played a recorded match in the window (kudos given or not)."""
        conn = self._get_connection()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
            if not cols:
                return False
            since = (datetime.now(timezone.utc) - timedelta(days=KUDOS_WINDOW_DAYS)).strftime("%Y-%m-%d")
            sql = """
                SELECT 1 FROM match_records
                WHERE ((CAST(winner_id AS TEXT) = ? AND CAST(losser_id AS TEXT) = ?)
                    OR (CAST(winner_id AS TEXT) = ? AND CAST(losser_id AS TEXT) = ?))
                  AND timestamp >= ?
            """
            params = [giver_id, receiver_id, receiver_id, giver_id, since]
            if pairing_id and "pairing_id" in cols:
                sql += " AND pairing_id = ?"
                params.append(int(pairing_id))
            return conn.execute(sql + " LIMIT 1", params).fetchone() is not None
        finally:
            conn.close()

    # ── Writing ───────────────────────────────────────────────

    def give_kudos(
        self,
        *,
        giver_id: str,
        receiver_id: str,
        reasons: list[str],
        message: str | None = None,
        anonymous: bool = False,
        giver_name: str | None = None,
        receiver_name: str | None = None,
        pairing_id: int | None = None,
        source: str | None = None,
    ) -> dict:
        """Store a kudos tied to the players' latest unthanked match.

        Raises KudosError("no_match" | "already_given") when there's no match
        to tie it to. Returns {"kudos_id", "match_id"}.
        """
        giver_id, receiver_id = str(giver_id), str(receiver_id)
        match = self.find_kudos_match(giver_id, receiver_id, pairing_id)
        if not match and pairing_id and not self.has_recent_match(giver_id, receiver_id, pairing_id):
            # That pairing has no recorded match (some result paths don't
            # store it): any recent match between the two counts.
            pairing_id = None
            match = self.find_kudos_match(giver_id, receiver_id, None)
        if not match:
            if self.has_recent_match(giver_id, receiver_id, pairing_id):
                raise KudosError("already_given", "Kudos were already given for this match")
            raise KudosError(
                "no_match",
                f"No recorded match between these players in the last {KUDOS_WINDOW_DAYS} days",
            )
        conn = self._get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO player_kudos (
                    giver_id, giver_name, receiver_id, receiver_name, match_id,
                    pairing_id, match_type, reasons, message, anonymous, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    giver_id,
                    giver_name,
                    receiver_id,
                    receiver_name,
                    int(match["match_id"]),
                    match.get("pairing_id") or pairing_id or None,
                    match.get("match_type"),
                    json.dumps(list(reasons or [])),
                    (message or "").strip() or None,
                    1 if anonymous else 0,
                    source,
                ),
            )
            conn.commit()
            return {"kudos_id": cur.lastrowid, "match_id": int(match["match_id"])}
        except sqlite3.IntegrityError:
            raise KudosError("already_given", "Kudos were already given for this match")
        finally:
            conn.close()

    def set_hidden(self, kudos_id: int, hidden: bool) -> bool:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "UPDATE player_kudos SET hidden = ? WHERE id = ?", (1 if hidden else 0, int(kudos_id))
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ── Reading ───────────────────────────────────────────────

    def _row(self, row) -> dict:
        entry = dict(row)
        entry["reasons"] = self._reasons(row["reasons"])
        entry["anonymous"] = bool(row["anonymous"])
        entry["hidden"] = bool(row["hidden"])
        return entry

    def get_all_kudos(self, limit: int = 200, offset: int = 0) -> tuple[list[dict], int]:
        """Every kudos, newest first (admin list). Returns (rows, total_count)."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute("SELECT COUNT(*) FROM player_kudos").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM player_kudos ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [self._row(r) for r in rows], total
        finally:
            conn.close()

    def kudos_between(self, start: str, end: str) -> list[dict]:
        """Visible kudos with start <= created_at < end (UTC 'YYYY-MM-DD' strings)."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT * FROM player_kudos
                WHERE hidden = 0 AND created_at >= ? AND created_at < ?
                ORDER BY created_at DESC, id DESC
                """,
                (start, end),
            ).fetchall()
            return [self._row(r) for r in rows]
        finally:
            conn.close()

    def pick_player_of_the_day(self, day: date | None = None) -> dict | None:
        """Choose today's kudos Player of the Day.

        Candidates are players who received visible kudos in the
        POTD_LOOKBACK_DAYS days before ``day`` (today's kudos wait until
        tomorrow, so every server worker picks the same player all day).
        More different thanking players = a better chance. Players featured
        on the previous few days are skipped when someone else is available.
        Returns the player plus the kudos to show, or None.
        """
        day = day or datetime.now(timezone.utc).date()

        def candidates_for(d: date) -> dict[str, list[dict]]:
            start = (d - timedelta(days=POTD_LOOKBACK_DAYS)).isoformat()
            by_receiver: dict[str, list[dict]] = {}
            for k in self.kudos_between(start, d.isoformat()):
                by_receiver.setdefault(k["receiver_id"], []).append(k)
            return by_receiver

        def choose(d: date, exclude: set[str]) -> str | None:
            by_receiver = candidates_for(d)
            pool = {uid: ks for uid, ks in by_receiver.items() if uid not in exclude} or by_receiver
            if not pool:
                return None
            ids = sorted(pool)
            weights = [len({k["giver_id"] for k in pool[uid]}) for uid in ids]
            return random.Random(f"kudos-potd-{d.isoformat()}").choices(ids, weights=weights)[0]

        # Avoid repeating the last 3 days' picks (computed without their own
        # exclusions, which keeps this cheap and still deterministic).
        recent = {
            uid for uid in (choose(day - timedelta(days=n), set()) for n in range(1, 4)) if uid
        }
        winner = choose(day, recent)
        if not winner:
            return None
        kudos = candidates_for(day)[winner]
        # Show the newest kudos that has a written message, else the newest one.
        featured = next((k for k in kudos if k.get("message")), kudos[0])
        givers = {k["giver_id"] for k in kudos}
        reason_counts: dict[str, int] = {}
        for k in kudos:
            for r in k["reasons"]:
                reason_counts[r] = reason_counts.get(r, 0) + 1
        top_reasons = [r for r, _ in sorted(reason_counts.items(), key=lambda x: (-x[1], x[0]))]
        return {
            "user_id": winner,
            "receiver_name": featured.get("receiver_name"),
            "kudos_count": len(kudos),
            "giver_count": len(givers),
            "top_reasons": top_reasons,
            "featured": featured,
        }
