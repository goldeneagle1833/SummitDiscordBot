"""Answers from Sorcery Online's one-time game lookup (Season 8 backfill).

PSO's ``/api/internal/summit/game-lookup`` matches a Summit match to the PSO
game it came from. It is a one-time backfill, so every answer is kept here
(``found``, ``not_found`` and ``ambiguous`` alike) and pages read from this
table, never from PSO.

Each player's replay link is their own view of the game and plays even when
they set it to private on PSO, so it is only ever shown to that player (see
services.replays.own_backfilled_replays).
"""

import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH

SCHEMA = """CREATE TABLE IF NOT EXISTS pso_game_lookups (
    match_id INTEGER PRIMARY KEY,          -- match_records rowid
    status TEXT NOT NULL,                  -- found / not_found / ambiguous / error
    candidates INTEGER,                    -- ambiguous: tables that matched
    error TEXT,                            -- error: HTTP status and message
    winner_id TEXT,
    loser_id TEXT,
    played_at TEXT,                        -- what we sent, UTC ISO 8601
    pso_game_id TEXT,
    matched_by TEXT,                       -- both_players / one_player
    started_at TEXT,
    finished_at TEXT,
    duration_seconds INTEGER,
    minutes_from_played_at INTEGER,
    pso_source TEXT,                       -- summit / pso / table
    pso_queue_type TEXT,
    pso_winner_id TEXT,                    -- NULL when PSO recorded no winner
    winner_went_first INTEGER,             -- 1 / 0 / NULL (PSO couldn't tell)
    winner_avatar TEXT,
    loser_avatar TEXT,
    winner_replay_url TEXT,                -- private: winner only
    loser_replay_url TEXT,                 -- private: loser only
    response_json TEXT,
    looked_up_at TEXT NOT NULL,
    applied_at TEXT                        -- when play/draw was copied to match_records
)"""


class PsoGameLookupRepository:
    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def looked_up_ids(self, statuses: tuple[str, ...] | None = None) -> set[int]:
        try:
            with self._connect() as conn:
                if statuses:
                    marks = ",".join("?" * len(statuses))
                    rows = conn.execute(
                        f"SELECT match_id FROM pso_game_lookups WHERE status IN ({marks})", statuses
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT match_id FROM pso_game_lookups").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {r[0] for r in rows}

    def save(self, row: dict) -> None:
        cols = list(row)
        with self._connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO pso_game_lookups ({', '.join(cols)})"
                f" VALUES ({', '.join('?' * len(cols))})",
                [row[c] for c in cols],
            )

    def all(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM pso_game_lookups ORDER BY match_id"
            ).fetchall()]

    def replays_for(self, match_ids) -> dict[int, dict]:
        """{match_id: {winner_id, loser_id, winner_replay_url, loser_replay_url}} for found games."""
        ids = sorted({int(m) for m in match_ids if m is not None})
        if not ids:
            return {}
        out = {}
        try:
            with self._connect() as conn:
                for start in range(0, len(ids), 500):
                    chunk = ids[start:start + 500]
                    rows = conn.execute(
                        "SELECT match_id, winner_id, loser_id, winner_replay_url, loser_replay_url"
                        " FROM pso_game_lookups WHERE status = 'found'"
                        f" AND match_id IN ({','.join('?' * len(chunk))})",
                        chunk,
                    ).fetchall()
                    out.update({r["match_id"]: dict(r) for r in rows})
        except sqlite3.OperationalError:
            return {}  # Backfill never ran here
        return out
