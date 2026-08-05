"""Repository for card catalog database access."""

import json
import sqlite3
from pathlib import Path

from webapp_config import ELO_DB_PATH


class CardCatalogRepository:
    """Data access for the card_catalog table in elo.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or ELO_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_all_cards(self) -> list[dict]:
        """Get all cards from the catalog."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT name, card_type, rarity, elements, sub_types, cost, attack, "
            "defence, life, threshold_air, threshold_earth, threshold_fire, "
            "threshold_water, rules_text, sets_json "
            "FROM card_catalog ORDER BY name COLLATE NOCASE"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_card_names(self) -> list[str]:
        """Get sorted list of all card names."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT name FROM card_catalog ORDER BY name COLLATE NOCASE"
        ).fetchall()
        conn.close()
        return [r["name"] for r in rows]

    def get_card(self, name: str) -> dict | None:
        """Get a single card by name (case-insensitive)."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM card_catalog WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def search_cards(self, query: str, limit: int = 20) -> list[str]:
        """Search card names containing query string."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT name FROM card_catalog WHERE name LIKE ? COLLATE NOCASE "
            "ORDER BY name COLLATE NOCASE LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        conn.close()
        return [r["name"] for r in rows]

    def get_card_metadata(self, card_name: str) -> dict:
        """Get type/element/rarity for a card name (used by card_points)."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT card_type, elements, rarity FROM card_catalog "
            "WHERE name = ? COLLATE NOCASE",
            (card_name,),
        ).fetchone()
        conn.close()
        if not row:
            return {}
        return {"type": row["card_type"], "element": row["elements"], "rarity": row["rarity"]}

    def get_card_count(self) -> int:
        """Get total number of cards in the catalog."""
        conn = self._get_connection()
        row = conn.execute("SELECT COUNT(*) as cnt FROM card_catalog").fetchone()
        conn.close()
        return row["cnt"]

    def get_card_elements_map(self) -> dict[str, set[str]]:
        """Get card name -> set of elements mapping (used by cards.py)."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT name, elements FROM card_catalog WHERE elements != '' AND elements != 'None'"
        ).fetchall()
        conn.close()
        return {
            row["name"].lower(): set(e.strip() for e in row["elements"].split(",") if e.strip())
            for row in rows
        }

    def get_all_cards_full_json(self) -> list[dict]:
        """Get all cards with full raw JSON (for compatibility with All_Cards_Array consumers)."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT raw_json FROM card_catalog ORDER BY name COLLATE NOCASE"
        ).fetchall()
        conn.close()
        return [json.loads(r["raw_json"]) for r in rows]

    # --- Sync operations ---

    def upsert_card(self, card_data: dict) -> str:
        """Insert or update a card from API data. Returns 'added', 'updated', or 'unchanged'."""
        name = card_data.get("name", "").strip()
        if not name:
            return "unchanged"

        guardian = card_data.get("guardian", {})
        thresholds = guardian.get("thresholds", {})

        conn = self._get_connection()
        existing = conn.execute(
            "SELECT raw_json FROM card_catalog WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()

        raw_json = json.dumps(card_data, ensure_ascii=False, sort_keys=True)

        if existing:
            if existing["raw_json"] == raw_json:
                conn.close()
                return "unchanged"
            conn.execute(
                "UPDATE card_catalog SET card_type=?, rarity=?, elements=?, sub_types=?, "
                "cost=?, attack=?, defence=?, life=?, threshold_air=?, threshold_earth=?, "
                "threshold_fire=?, threshold_water=?, rules_text=?, sets_json=?, raw_json=?, "
                "updated_at=strftime('%Y-%m-%d %H:%M:%S', 'now') "
                "WHERE name = ? COLLATE NOCASE",
                (
                    guardian.get("type", ""),
                    guardian.get("rarity", ""),
                    card_data.get("elements", ""),
                    card_data.get("subTypes", ""),
                    guardian.get("cost"),
                    guardian.get("attack"),
                    guardian.get("defence"),
                    guardian.get("life"),
                    thresholds.get("air", 0),
                    thresholds.get("earth", 0),
                    thresholds.get("fire", 0),
                    thresholds.get("water", 0),
                    guardian.get("rulesText", ""),
                    json.dumps(card_data.get("sets", []), ensure_ascii=False),
                    raw_json,
                    name,
                ),
            )
            conn.commit()
            conn.close()
            return "updated"
        else:
            conn.execute(
                "INSERT INTO card_catalog (name, card_type, rarity, elements, sub_types, "
                "cost, attack, defence, life, threshold_air, threshold_earth, "
                "threshold_fire, threshold_water, rules_text, sets_json, raw_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    guardian.get("type", ""),
                    guardian.get("rarity", ""),
                    card_data.get("elements", ""),
                    card_data.get("subTypes", ""),
                    guardian.get("cost"),
                    guardian.get("attack"),
                    guardian.get("defence"),
                    guardian.get("life"),
                    thresholds.get("air", 0),
                    thresholds.get("earth", 0),
                    thresholds.get("fire", 0),
                    thresholds.get("water", 0),
                    guardian.get("rulesText", ""),
                    json.dumps(card_data.get("sets", []), ensure_ascii=False),
                    raw_json,
                ),
            )
            conn.commit()
            conn.close()
            return "added"

    def remove_cards_not_in(self, card_names: set[str]) -> list[str]:
        """Remove cards from catalog that are no longer in the API. Returns removed names."""
        conn = self._get_connection()
        rows = conn.execute("SELECT name FROM card_catalog").fetchall()
        existing_names = {r["name"] for r in rows}

        # Case-insensitive comparison
        api_names_lower = {n.lower() for n in card_names}
        to_remove = [n for n in existing_names if n.lower() not in api_names_lower]

        for name in to_remove:
            conn.execute("DELETE FROM card_catalog WHERE name = ?", (name,))

        if to_remove:
            conn.commit()
        conn.close()
        return to_remove

    def log_sync(self, added: int, updated: int, removed: int, total: int):
        """Log a sync event."""
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO card_catalog_sync_log (cards_added, cards_updated, cards_removed, total_cards) "
            "VALUES (?, ?, ?, ?)",
            (added, updated, removed, total),
        )
        conn.commit()
        conn.close()

    def bulk_load_from_json(self, cards: list[dict]) -> tuple[int, int]:
        """Bulk load cards from a JSON array (for initial seeding). Returns (added, updated)."""
        added = updated = 0
        for card_data in cards:
            result = self.upsert_card(card_data)
            if result == "added":
                added += 1
            elif result == "updated":
                updated += 1
        return added, updated
