"""Data access layer for user-created seasons."""

import sqlite3
from datetime import datetime

from webapp_config import MATCH_RECORDS_DB_PATH


class SeasonsRepository:
    """Repository for seasons, season_members, and season_match_elo tables."""

    def __init__(self, db_path=None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)

    def _get_connection(self):
        return sqlite3.connect(self._db_path)

    def ensure_tables(self):
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS seasons (
                season_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id TEXT NOT NULL,
                creator_display_name TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                k_value INTEGER NOT NULL DEFAULT 32,
                base_elo INTEGER NOT NULL DEFAULT 1500,
                max_members INTEGER,
                region TEXT,
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_seasons_creator ON seasons(creator_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_seasons_status ON seasons(status)
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS season_members (
                season_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                season_elo INTEGER NOT NULL DEFAULT 1500,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (season_id, user_id)
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_season_members_user ON season_members(user_id)
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS season_match_elo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL,
                match_id TEXT NOT NULL,
                reporter_id TEXT,
                winner_id TEXT NOT NULL,
                loser_id TEXT NOT NULL,
                winner_display_name TEXT NOT NULL,
                loser_display_name TEXT NOT NULL,
                did_win INTEGER NOT NULL,
                winner_went_first TEXT,
                loser_went_first TEXT,
                match_time INTEGER,
                match_comment TEXT,
                curiosa_url_winner TEXT,
                curiosa_url_loser TEXT,
                json_deck_data_winner TEXT,
                json_deck_data_loser TEXT,
                winner_elo_before INTEGER NOT NULL,
                winner_elo_after INTEGER NOT NULL,
                winner_elo_change INTEGER NOT NULL,
                loser_elo_before INTEGER NOT NULL,
                loser_elo_after INTEGER NOT NULL,
                loser_elo_change INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'Web',
                match_type TEXT NOT NULL DEFAULT 'ranked',
                timestamp TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_season_match_elo_season ON season_match_elo(season_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_season_match_elo_match ON season_match_elo(match_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_season_match_elo_winner ON season_match_elo(winner_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_season_match_elo_loser ON season_match_elo(loser_id)
        """)

        conn.commit()
        conn.close()

    # ── Season CRUD ──────────────────────────────────────────────

    def create_season(self, creator_id, creator_display_name, title,
                      description, start_date, end_date, k_value=32,
                      base_elo=1500, max_members=None, region=None):
        conn = self._get_connection()
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute(
            """INSERT INTO seasons
               (creator_id, creator_display_name, title, description,
                start_date, end_date, status, k_value, base_elo,
                max_members, region, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
            (creator_id, creator_display_name, title, description,
             start_date, end_date, k_value, base_elo, max_members,
             region, now),
        )
        season_id = cur.lastrowid
        conn.commit()
        conn.close()
        return season_id

    def get_season_by_id(self, season_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT season_id, creator_id, creator_display_name, title,
                      description, start_date, end_date, status, k_value,
                      base_elo, max_members, region, created_at
               FROM seasons
               WHERE season_id = ? AND status != 'deleted'""",
            (season_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "season_id": row[0], "creator_id": row[1],
            "creator_display_name": row[2], "title": row[3],
            "description": row[4], "start_date": row[5],
            "end_date": row[6], "status": row[7], "k_value": row[8],
            "base_elo": row[9], "max_members": row[10],
            "region": row[11], "created_at": row[12],
        }

    def update_season(self, season_id, **fields):
        allowed = {"start_date", "end_date", "description", "k_value",
                    "max_members", "region"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [season_id]
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE seasons SET {set_clause} WHERE season_id = ?",
            values,
        )
        conn.commit()
        conn.close()

    def end_season(self, season_id):
        conn = self._get_connection()
        cur = conn.cursor()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cur.execute(
            "UPDATE seasons SET status = 'ended', end_date = ? WHERE season_id = ?",
            (today, season_id),
        )
        conn.commit()
        conn.close()

    def delete_season(self, season_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE seasons SET status = 'deleted' WHERE season_id = ?",
            (season_id,),
        )
        cur.execute(
            "DELETE FROM season_members WHERE season_id = ?",
            (season_id,),
        )
        conn.commit()
        conn.close()

    def search_seasons(self, query, user_id):
        conn = self._get_connection()
        cur = conn.cursor()
        like_pattern = f"%{query}%" if query else "%"
        cur.execute(
            """SELECT s.season_id, s.title, s.description, s.start_date,
                      s.end_date, s.creator_display_name, s.max_members,
                      s.region,
                      COUNT(sm.user_id) AS member_count,
                      MAX(CASE WHEN sm.user_id = ? THEN 1 ELSE 0 END) AS is_member
               FROM seasons s
               LEFT JOIN season_members sm ON s.season_id = sm.season_id
               WHERE s.status = 'active'
                 AND s.end_date >= date('now')
                 AND s.title LIKE ?
               GROUP BY s.season_id
               ORDER BY s.start_date ASC""",
            (user_id, like_pattern),
        )
        rows = cur.fetchall()
        conn.close()
        results = []
        for row in rows:
            results.append({
                "season_id": row[0], "title": row[1], "description": row[2],
                "start_date": row[3], "end_date": row[4],
                "creator_name": row[5], "max_members": row[6],
                "region": row[7], "member_count": row[8],
                "is_member": bool(row[9]),
            })
        return results

    # ── Membership ───────────────────────────────────────────────

    def add_member(self, season_id, user_id, display_name, starting_elo):
        conn = self._get_connection()
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute(
            """INSERT INTO season_members
               (season_id, user_id, display_name, season_elo, wins, losses, joined_at)
               VALUES (?, ?, ?, ?, 0, 0, ?)""",
            (season_id, user_id, display_name, starting_elo, now),
        )
        conn.commit()
        conn.close()

    def remove_member(self, season_id, user_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM season_members WHERE season_id = ? AND user_id = ?",
            (season_id, user_id),
        )
        conn.commit()
        conn.close()

    def get_user_active_season(self, user_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT s.season_id, s.creator_id, s.creator_display_name,
                      s.title, s.description, s.start_date, s.end_date,
                      s.status, s.k_value, s.base_elo, s.max_members,
                      s.region, s.created_at,
                      sm.season_elo, sm.wins, sm.losses
               FROM season_members sm
               JOIN seasons s ON sm.season_id = s.season_id
               WHERE sm.user_id = ?
                 AND s.status = 'active'
                 AND s.end_date >= date('now')""",
            (user_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "season_id": row[0], "creator_id": row[1],
            "creator_display_name": row[2], "title": row[3],
            "description": row[4], "start_date": row[5],
            "end_date": row[6], "status": row[7], "k_value": row[8],
            "base_elo": row[9], "max_members": row[10],
            "region": row[11], "created_at": row[12],
            "season_elo": row[13], "wins": row[14], "losses": row[15],
        }

    def get_season_members(self, season_id):
        conn = self._get_connection()
        cur = conn.cursor()
        # Get creator_id for is_creator flag
        cur.execute(
            "SELECT creator_id FROM seasons WHERE season_id = ?",
            (season_id,),
        )
        creator_row = cur.fetchone()
        creator_id = creator_row[0] if creator_row else None

        cur.execute(
            """SELECT user_id, display_name, season_elo, wins, losses,
                      RANK() OVER (ORDER BY season_elo DESC) AS rank
               FROM season_members
               WHERE season_id = ?""",
            (season_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "user_id": row[0], "display_name": row[1],
                "season_elo": row[2], "wins": row[3], "losses": row[4],
                "rank": row[5], "is_creator": row[0] == creator_id,
            }
            for row in rows
        ]

    def get_member_count(self, season_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM season_members WHERE season_id = ?",
            (season_id,),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count

    # ── Season ELO ───────────────────────────────────────────────

    def get_shared_active_season(self, user_id_1, user_id_2):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT s.season_id, s.creator_id, s.title, s.k_value,
                      s.base_elo, s.start_date, s.end_date
               FROM seasons s
               INNER JOIN season_members sm1
                   ON s.season_id = sm1.season_id
               INNER JOIN season_members sm2
                   ON s.season_id = sm2.season_id
               WHERE sm1.user_id = ? AND sm2.user_id = ?
                 AND s.status = 'active'
                 AND s.start_date <= date('now')
                 AND s.end_date >= date('now')""",
            (user_id_1, user_id_2),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "season_id": row[0], "creator_id": row[1], "title": row[2],
            "k_value": row[3], "base_elo": row[4],
            "start_date": row[5], "end_date": row[6],
        }

    def get_member_elo(self, season_id, user_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT season_elo FROM season_members WHERE season_id = ? AND user_id = ?",
            (season_id, user_id),
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def update_member_elo_and_record(self, season_id, user_id, new_elo, is_winner):
        conn = self._get_connection()
        cur = conn.cursor()
        if is_winner:
            cur.execute(
                """UPDATE season_members
                   SET season_elo = ?, wins = wins + 1
                   WHERE season_id = ? AND user_id = ?""",
                (new_elo, season_id, user_id),
            )
        else:
            cur.execute(
                """UPDATE season_members
                   SET season_elo = ?, losses = losses + 1
                   WHERE season_id = ? AND user_id = ?""",
                (new_elo, season_id, user_id),
            )
        conn.commit()
        conn.close()

    def insert_season_match_record(self, season_id, match_id, match_data,
                                   winner_elo_before, winner_elo_after,
                                   winner_elo_change, loser_elo_before,
                                   loser_elo_after, loser_elo_change):
        conn = self._get_connection()
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute(
            """INSERT INTO season_match_elo
               (season_id, match_id, reporter_id, winner_id, loser_id,
                winner_display_name, loser_display_name, did_win,
                winner_went_first, loser_went_first, match_time,
                match_comment, curiosa_url_winner, curiosa_url_loser,
                json_deck_data_winner, json_deck_data_loser,
                winner_elo_before, winner_elo_after, winner_elo_change,
                loser_elo_before, loser_elo_after, loser_elo_change,
                source, match_type, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                season_id, match_id,
                match_data.get("reporter_id"),
                match_data.get("winner_id"),
                match_data.get("loser_id"),
                match_data.get("winner_display_name", ""),
                match_data.get("loser_display_name", ""),
                match_data.get("did_win", 1),
                match_data.get("winner_went_first"),
                match_data.get("loser_went_first"),
                match_data.get("match_time"),
                match_data.get("match_comment"),
                match_data.get("curiosa_url_winner"),
                match_data.get("curiosa_url_loser"),
                match_data.get("json_deck_data_winner"),
                match_data.get("json_deck_data_loser"),
                winner_elo_before, winner_elo_after, winner_elo_change,
                loser_elo_before, loser_elo_after, loser_elo_change,
                match_data.get("source", "Web"),
                match_data.get("match_type", "ranked"),
                now,
            ),
        )
        conn.commit()
        conn.close()
