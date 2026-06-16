"""Repository for saved deck builder decks."""

import json
import sqlite3
from pathlib import Path

from webapp_config import DECK_BUILDER_DB_PATH


class DeckBuilderRepository:
    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or DECK_BUILDER_DB_PATH)

    def _conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_deck(self, user_id: str, name: str, mainboard: list, sideboard: list,
                  card_tags: dict, avatar: dict | None = None, source_url: str | None = None) -> int:
        """Save a new deck. Returns the deck id."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO saved_decks (user_id, name, source_url, avatar_json, mainboard_json, sideboard_json, card_tags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(user_id), name, source_url, json.dumps(avatar), json.dumps(mainboard),
             json.dumps(sideboard), json.dumps(card_tags)),
        )
        deck_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return deck_id

    def update_deck(self, deck_id: int, user_id: str, name: str, mainboard: list,
                    sideboard: list, card_tags: dict, avatar: dict | None = None) -> bool:
        """Update an existing deck. Returns True if updated."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE saved_decks
               SET name = ?, avatar_json = ?, mainboard_json = ?, sideboard_json = ?,
                   card_tags_json = ?, updated_at = datetime('now')
               WHERE id = ? AND user_id = ?""",
            (name, json.dumps(avatar), json.dumps(mainboard), json.dumps(sideboard),
             json.dumps(card_tags), deck_id, str(user_id)),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def list_decks(self, user_id: str, search: str | None = None) -> list[dict]:
        """List all decks for a user, optionally filtered by name search."""
        conn = self._conn()
        cursor = conn.cursor()
        if search:
            cursor.execute(
                """SELECT id, name, source_url, created_at, updated_at
                   FROM saved_decks WHERE user_id = ? AND name LIKE ?
                   ORDER BY updated_at DESC""",
                (str(user_id), f"%{search}%"),
            )
        else:
            cursor.execute(
                """SELECT id, name, source_url, created_at, updated_at
                   FROM saved_decks WHERE user_id = ? ORDER BY updated_at DESC""",
                (str(user_id),),
            )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_deck(self, deck_id: int, user_id: str) -> dict | None:
        """Get a single deck by id, only if owned by user_id."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM saved_decks WHERE id = ? AND user_id = ?", (deck_id, str(user_id)))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["avatar"] = json.loads(d.pop("avatar_json") or "null")
        d["mainboard"] = json.loads(d.pop("mainboard_json"))
        d["sideboard"] = json.loads(d.pop("sideboard_json"))
        d["card_tags"] = json.loads(d.pop("card_tags_json"))
        return d

    def delete_deck(self, deck_id: int, user_id: str) -> bool:
        """Delete a deck. Returns True if deleted."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_decks WHERE id = ? AND user_id = ?", (deck_id, str(user_id)))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
