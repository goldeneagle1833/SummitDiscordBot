"""
Migration: Create card_catalog table in elo.db.

Stores the full card database from the Sorcery TCG API, replacing the static
All_Cards_Array.json file. A daily sync task in the Discord bot keeps it current.

Run with: python migrations/create_card_catalog_table.py
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import ALL_CARDS_PATH, ELO_DB_PATH

logger = logging.getLogger(__name__)


def create_card_catalog_table():
    """Create card_catalog table if it doesn't exist."""
    conn = sqlite3.connect(str(ELO_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            card_type TEXT NOT NULL DEFAULT '',
            rarity TEXT NOT NULL DEFAULT '',
            elements TEXT NOT NULL DEFAULT '',
            sub_types TEXT NOT NULL DEFAULT '',
            cost INTEGER,
            attack INTEGER,
            defence INTEGER,
            life INTEGER,
            threshold_air INTEGER NOT NULL DEFAULT 0,
            threshold_earth INTEGER NOT NULL DEFAULT 0,
            threshold_fire INTEGER NOT NULL DEFAULT 0,
            threshold_water INTEGER NOT NULL DEFAULT 0,
            rules_text TEXT NOT NULL DEFAULT '',
            sets_json TEXT NOT NULL DEFAULT '[]',
            raw_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_catalog_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            cards_added INTEGER NOT NULL DEFAULT 0,
            cards_updated INTEGER NOT NULL DEFAULT 0,
            cards_removed INTEGER NOT NULL DEFAULT 0,
            total_cards INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()

    # Seed from All_Cards_Array.json if table is empty
    count = cursor.execute("SELECT COUNT(*) FROM card_catalog").fetchone()[0]
    if count == 0 and ALL_CARDS_PATH.exists():
        try:
            with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
                cards = json.load(f)
            seeded = 0
            for card_data in cards:
                name = card_data.get("name", "").strip()
                if not name:
                    continue
                guardian = card_data.get("guardian", {})
                thresholds = guardian.get("thresholds", {})
                raw_json = json.dumps(card_data, ensure_ascii=False, sort_keys=True)
                cursor.execute(
                    "INSERT OR IGNORE INTO card_catalog "
                    "(name, card_type, rarity, elements, sub_types, cost, attack, defence, "
                    "life, threshold_air, threshold_earth, threshold_fire, threshold_water, "
                    "rules_text, sets_json, raw_json) "
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
                seeded += 1
            conn.commit()
            logger.info(f"Seeded card_catalog with {seeded} cards from All_Cards_Array.json")
        except Exception as e:
            logger.error(f"Failed to seed card_catalog from JSON: {e}")

    conn.close()
    logger.info("card_catalog and card_catalog_sync_log tables ensured.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_card_catalog_table()
    print("Done.")
