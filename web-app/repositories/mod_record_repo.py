"""A player's full moderation record for the Mod Tools player page.

Reads tables the Discord bot writes (discord-bot/repositories/moderation_repo.py):
``moderation_notes`` (Note button), ``moderation_group_chats`` (Group chat,
with the saved transcript once closed) and ``moderation_alerts`` rows of kind
``repeat`` (repeat-offender heads-ups). Plus ``player_reports``,
``blocked_users`` and ``moderation_actions``. Any table may be missing on a
fresh database, so every read checks first.
"""

import json
import sqlite3
from pathlib import Path

import webapp_config


def _reasons(raw) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


class ModRecordRepository:
    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or webapp_config.MATCH_RECORDS_DB_PATH)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _has(conn, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone() is not None

    @staticmethod
    def _cols(conn, table: str) -> set[str]:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def ensure_notes_table(self):
        """Same schema as the bot's, so notes can be added from the website first."""
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS moderation_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    by_id TEXT,
                    by_name TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_notes_target ON moderation_notes (target_id)")
            conn.commit()
        finally:
            conn.close()

    def add_note(self, target_id, note, by_id, by_name) -> int:
        self.ensure_notes_table()
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO moderation_notes (target_id, note, by_id, by_name) VALUES (?, ?, ?, ?)",
                (str(target_id), note, str(by_id), by_name),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def record(self, target_id) -> dict:
        """Everything on record about ``target_id``, newest first in each list."""
        uid = str(target_id)
        out = {"reports": [], "reports_filed": 0, "blocks": [], "actions": [], "notes": [],
               "chats": [], "flags": []}
        conn = self._connect()
        try:
            if self._has(conn, "player_reports"):
                source = "source" if "source" in self._cols(conn, "player_reports") else "NULL AS source"
                for row in conn.execute(
                    f"SELECT id, reporter_id, reporter_name, reported_name, pairing_id, match_type, "
                    f"reasons, details, {source}, created_at FROM player_reports "
                    "WHERE reported_id = ? ORDER BY id DESC",
                    (uid,),
                ).fetchall():
                    entry = dict(row)
                    entry["reasons"] = _reasons(row["reasons"])
                    out["reports"].append(entry)
                out["reports_filed"] = conn.execute(
                    "SELECT COUNT(*) FROM player_reports WHERE reporter_id = ?", (uid,)
                ).fetchone()[0]
            if self._has(conn, "blocked_users"):
                out["blocks"] = [dict(r) for r in conn.execute(
                    "SELECT user_id, reason, created_at FROM blocked_users "
                    "WHERE blocked_user_id = ? ORDER BY created_at DESC",
                    (uid,),
                ).fetchall()]
            if self._has(conn, "moderation_actions"):
                out["actions"] = [dict(r) for r in conn.execute(
                    "SELECT id, action, duration_minutes, duration_label, reason, source_kind, source_ref, "
                    "by_name, via, created_at FROM moderation_actions WHERE target_id = ? ORDER BY id DESC",
                    (uid,),
                ).fetchall()]
            if self._has(conn, "moderation_notes"):
                out["notes"] = [dict(r) for r in conn.execute(
                    "SELECT id, note, by_name, created_at FROM moderation_notes "
                    "WHERE target_id = ? ORDER BY id DESC",
                    (uid,),
                ).fetchall()]
            if self._has(conn, "moderation_group_chats"):
                cols = self._cols(conn, "moderation_group_chats")
                extra = ", ".join(c if c in cols else f"NULL AS {c}" for c in ("transcript", "message_count"))
                out["chats"] = [dict(r) for r in conn.execute(
                    "SELECT id, channel_id, source_kind, source_ref, opened_by_name, created_at, closed_at, "
                    f"closed_by_name, {extra} FROM moderation_group_chats WHERE target_id = ? ORDER BY id DESC",
                    (uid,),
                ).fetchall()]
            if self._has(conn, "moderation_alerts"):
                out["flags"] = [
                    {"created_at": r["alerted_at"]}
                    for r in conn.execute(
                        "SELECT alerted_at FROM moderation_alerts WHERE kind = 'repeat' AND ref LIKE ? "
                        "ORDER BY alerted_at DESC",
                        (f"{uid}|%",),
                    ).fetchall()
                ]
        finally:
            conn.close()
        return out


# ── website -> bot requests (same tables as discord-bot/repositories/moderation_repo.py) ──


class ModRequestsRepository:
    """Queues the bot works every 30 s: player summary posts and match flips."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or webapp_config.MATCH_RECORDS_DB_PATH)
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS moderation_summary_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id TEXT NOT NULL,
                    requested_by_id TEXT,
                    requested_by_name TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    done_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS moderation_match_flips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL,
                    target_id TEXT NOT NULL,
                    requested_by_id TEXT,
                    requested_by_name TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    done_at TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def request_summary(self, target_id, by_id, by_name) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO moderation_summary_requests (target_id, requested_by_id, requested_by_name) "
                "VALUES (?, ?, ?)",
                (str(target_id), str(by_id), by_name),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def player_matches(self, target_id, table: str, limit: int = 200) -> list[dict]:
        """The player's matches in the current match table, newest first."""
        uid = str(target_id)
        conn = self._connect()
        try:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if not cols:
                return []
            opt = ", ".join(c if c in cols else f"NULL AS {c}" for c in ("match_type", "source", "winner_avatar", "loser_avatar"))
            rows = conn.execute(
                f"SELECT rowid AS id, timestamp, winner_id, winner_display_name, losser_id, losser_display_name, "
                f"{opt} FROM {table} WHERE CAST(winner_id AS TEXT) = ? OR CAST(losser_id AS TEXT) = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (uid, uid, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def flips_for(self, target_id) -> list[dict]:
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT id, match_id, status, result, requested_by_name, created_at, done_at "
                "FROM moderation_match_flips WHERE target_id = ? ORDER BY id DESC",
                (str(target_id),),
            ).fetchall()]
        finally:
            conn.close()

    def request_flips(self, target_id, match_ids, by_id, by_name) -> int:
        """Queue flips, skipping matches that already have one pending."""
        conn = self._connect()
        try:
            pending = {r[0] for r in conn.execute(
                "SELECT match_id FROM moderation_match_flips WHERE status = 'pending'"
            ).fetchall()}
            added = 0
            for mid in match_ids:
                if int(mid) in pending:
                    continue
                conn.execute(
                    "INSERT INTO moderation_match_flips (match_id, target_id, requested_by_id, requested_by_name) "
                    "VALUES (?, ?, ?, ?)",
                    (int(mid), str(target_id), str(by_id), by_name),
                )
                added += 1
            conn.commit()
            return added
        finally:
            conn.close()

    # ── Partner (Play Sorcery Online) match corrections ──────────────

    def find_match(self, table: str, match_id=None, pairing_id=None) -> list[dict]:
        """A match by its ID (the rowid) or by the Summit pairing ID it was played for.

        A pairing can, rarely, have more than one recorded match, so this
        returns every hit, newest first.
        """
        conn = self._connect()
        try:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if not cols:
                return []
            pairing_col = "pairing_id" if "pairing_id" in cols else "NULL AS pairing_id"
            opt = ", ".join(c if c in cols else f"NULL AS {c}" for c in ("match_type", "source"))
            sql = (
                f"SELECT rowid AS id, timestamp, CAST(winner_id AS TEXT) AS winner_id, winner_display_name, "
                f"CAST(losser_id AS TEXT) AS loser_id, losser_display_name AS loser_display_name, "
                f"{pairing_col}, {opt} FROM {table} WHERE "
            )
            if match_id is not None:
                rows = conn.execute(sql + "rowid = ?", (int(match_id),)).fetchall()
            elif "pairing_id" in cols:
                rows = conn.execute(sql + "pairing_id = ? ORDER BY timestamp DESC", (int(pairing_id),)).fetchall()
            else:
                rows = []
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def queue_flip(self, match_id, target_id, by_id, by_name) -> tuple[int, bool]:
        """Queue one flip. Returns (request id, newly queued); an already
        pending flip of the same match is reused, never doubled."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id FROM moderation_match_flips WHERE match_id = ? AND status = 'pending' "
                "ORDER BY id LIMIT 1",
                (int(match_id),),
            ).fetchone()
            if row:
                return row["id"], False
            cur = conn.execute(
                "INSERT INTO moderation_match_flips (match_id, target_id, requested_by_id, requested_by_name) "
                "VALUES (?, ?, ?, ?)",
                (int(match_id), str(target_id), str(by_id), by_name),
            )
            conn.commit()
            return cur.lastrowid, True
        finally:
            conn.close()

    def pending_flip_for_match(self, match_id) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, match_id, status, result, requested_by_id, requested_by_name, created_at, done_at "
                "FROM moderation_match_flips WHERE match_id = ? AND status = 'pending' ORDER BY id LIMIT 1",
                (int(match_id),),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_flip(self, flip_id) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, match_id, target_id, status, result, requested_by_id, requested_by_name, "
                "created_at, done_at FROM moderation_match_flips WHERE id = ?",
                (int(flip_id),),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
