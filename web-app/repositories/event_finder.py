"""Find a player at an in-person event: hall maps and each person's shared spot.

Two tables in match_records.db:

* ``event_maps``: one per event, set up by admins. A floor plan image, the
  event dates, the daily hours sharing is shown (in the venue's time zone)
  and a few named quick spots (Booth, Stage...) with their place on the map.
* ``finder_shares``: one row per person. Which map they are on, whether they
  are sharing, whether they appear on the event's public list, and their
  current spot: a pin (x/y as 0-100 percent of the map) and/or a label.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone

import webapp_config

DEFAULT_DAILY_START = "08:00"
DEFAULT_DAILY_END = "20:00"
DEFAULT_TIMEZONE = "America/New_York"

MAP_FIELDS = (
    "name", "image_url", "start_date", "end_date",
    "daily_start", "daily_end", "timezone", "spots",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_token() -> str:
    return secrets.token_urlsafe(12)


class EventFinderRepository:
    def __init__(self, db_path=None):
        self._explicit_path = db_path

    @property
    def _db_path(self) -> str:
        return str(self._explicit_path or webapp_config.MATCH_RECORDS_DB_PATH)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE IF NOT EXISTS event_maps (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL,
                   image_url TEXT,
                   start_date TEXT NOT NULL,
                   end_date TEXT NOT NULL,
                   daily_start TEXT NOT NULL DEFAULT '08:00',
                   daily_end TEXT NOT NULL DEFAULT '20:00',
                   timezone TEXT NOT NULL DEFAULT 'America/New_York',
                   spots TEXT NOT NULL DEFAULT '[]',
                   created_at TEXT NOT NULL,
                   updated_at TEXT NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS finder_shares (
                   user_id TEXT PRIMARY KEY,
                   username TEXT,
                   avatar TEXT,
                   token TEXT NOT NULL UNIQUE,
                   map_id INTEGER,
                   sharing INTEGER NOT NULL DEFAULT 0,
                   listed INTEGER NOT NULL DEFAULT 0,
                   x REAL,
                   y REAL,
                   label TEXT,
                   note TEXT,
                   updated_at TEXT
               )"""
        )
        return conn

    # ------------------------------------------------------------------
    # Maps
    # ------------------------------------------------------------------

    @staticmethod
    def _map_row(row) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        try:
            d["spots"] = json.loads(d.get("spots") or "[]")
        except (TypeError, ValueError):
            d["spots"] = []
        return d

    def list_maps(self, include_past: bool = False, today: str | None = None) -> list[dict]:
        conn = self._conn()
        try:
            if include_past:
                rows = conn.execute(
                    "SELECT * FROM event_maps ORDER BY start_date DESC, id DESC"
                ).fetchall()
            else:
                today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
                # A day of slack so a venue behind UTC still sees its last day
                rows = conn.execute(
                    """SELECT * FROM event_maps WHERE date(end_date, '+1 day') >= ?
                       ORDER BY start_date, id""",
                    (today,),
                ).fetchall()
            return [self._map_row(r) for r in rows]
        finally:
            conn.close()

    def get_map(self, map_id) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM event_maps WHERE id = ?", (map_id,)).fetchone()
            return self._map_row(row)
        finally:
            conn.close()

    def create_map(self, **fields) -> dict:
        now = _now()
        values = {
            "name": fields.get("name") or "Event",
            "image_url": fields.get("image_url") or None,
            "start_date": fields["start_date"],
            "end_date": fields["end_date"],
            "daily_start": fields.get("daily_start") or DEFAULT_DAILY_START,
            "daily_end": fields.get("daily_end") or DEFAULT_DAILY_END,
            "timezone": fields.get("timezone") or DEFAULT_TIMEZONE,
            "spots": json.dumps(fields.get("spots") or []),
        }
        conn = self._conn()
        try:
            cur = conn.execute(
                f"""INSERT INTO event_maps ({", ".join(values)}, created_at, updated_at)
                    VALUES ({", ".join("?" for _ in values)}, ?, ?)""",
                (*values.values(), now, now),
            )
            conn.commit()
            map_id = cur.lastrowid
        finally:
            conn.close()
        return self.get_map(map_id)

    def update_map(self, map_id, **fields) -> dict | None:
        updates = {k: v for k, v in fields.items() if k in MAP_FIELDS}
        if "spots" in updates:
            updates["spots"] = json.dumps(updates["spots"] or [])
        if updates:
            conn = self._conn()
            try:
                sets = ", ".join(f"{k} = ?" for k in updates)
                conn.execute(
                    f"UPDATE event_maps SET {sets}, updated_at = ? WHERE id = ?",
                    (*updates.values(), _now(), map_id),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_map(map_id)

    def delete_map(self, map_id) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM event_maps WHERE id = ?", (map_id,))
            # Nobody keeps sharing on a map that no longer exists
            conn.execute(
                "UPDATE finder_shares SET map_id = NULL, sharing = 0 WHERE map_id = ?",
                (map_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    def get_share(self, user_id) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM finder_shares WHERE user_id = ?", (str(user_id),)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_or_create_share(self, user_id, username=None, avatar=None) -> dict:
        share = self.get_share(user_id)
        if share:
            if (username and username != share.get("username")) or (
                avatar and avatar != share.get("avatar")
            ):
                conn = self._conn()
                try:
                    conn.execute(
                        "UPDATE finder_shares SET username = COALESCE(?, username), "
                        "avatar = COALESCE(?, avatar) WHERE user_id = ?",
                        (username, avatar, str(user_id)),
                    )
                    conn.commit()
                finally:
                    conn.close()
                share = self.get_share(user_id)
            return share
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO finder_shares (user_id, username, avatar, token)
                   VALUES (?, ?, ?, ?)""",
                (str(user_id), username, avatar, _new_token()),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_share(user_id)

    def update_share(self, user_id, **fields) -> dict:
        """Change settings and/or the spot. Moving the pin or changing the
        label stamps ``updated_at`` so viewers see how fresh it is."""
        allowed = {"map_id", "sharing", "listed", "x", "y", "label", "note"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if any(k in updates for k in ("x", "y", "label", "note")) or (
            updates.get("sharing") in (1, True)
        ):
            updates["updated_at"] = _now()
        if updates:
            conn = self._conn()
            try:
                sets = ", ".join(f"{k} = ?" for k in updates)
                conn.execute(
                    f"UPDATE finder_shares SET {sets} WHERE user_id = ?",
                    (*updates.values(), str(user_id)),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_share(user_id)

    def new_link(self, user_id) -> dict:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE finder_shares SET token = ? WHERE user_id = ?",
                (_new_token(), str(user_id)),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_share(user_id)

    def get_share_by_token(self, token: str) -> dict | None:
        if not token:
            return None
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM finder_shares WHERE token = ?", (token,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def listed_on_map(self, map_id) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM finder_shares
                   WHERE map_id = ? AND sharing = 1 AND listed = 1
                   ORDER BY updated_at DESC""",
                (map_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
