"""
Migration: Create rumble.db tables for the Rumble bones/prizes feature.

Run with: python migrations/create_rumble_tables.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import RUMBLE_DB_PATH

logger = logging.getLogger(__name__)


def create_rumble_tables():
    """Create all Rumble tables if they don't exist."""
    conn = sqlite3.connect(str(RUMBLE_DB_PATH))
    cursor = conn.cursor()

    # Admins who can manage rumble bones/prizes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rumble_admins (
            discord_user_id TEXT PRIMARY KEY,
            display_name TEXT,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Bone balances per player
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rumble_bones (
            discord_user_id TEXT PRIMARY KEY,
            display_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Transaction log for all bone changes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rumble_bone_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_user_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            admin_user_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bone_transactions_user
        ON rumble_bone_transactions(discord_user_id)
    """)

    # Configurable earnings rates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rumble_earnings_config (
            key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            category TEXT NOT NULL,
            bones INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Seed default earnings config if empty
    cursor.execute("SELECT COUNT(*) FROM rumble_earnings_config")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ("round_loss", "Round Loss", "match", 1, 1),
            ("round_win", "Round Win", "match", 3, 2),
            ("round_tie", "Round Tie", "match", 2, 3),
            ("grovel", "Grovel (per season)", "match", 1, 4),
            ("place_1st", "1st Place", "placement", 13, 10),
            ("place_2nd", "2nd Place", "placement", 6, 11),
            ("place_3rd", "3rd Place", "placement", 6, 12),
            ("place_4th", "4th Place", "placement", 6, 13),
            ("fart_champ", "Fart Game Seasonal Champ", "outside", 13, 20),
            ("bad_movie_night", "Bad Movie Night Attendance", "outside", 6, 21),
        ]
        cursor.executemany(
            "INSERT INTO rumble_earnings_config (key, label, category, bones, sort_order) VALUES (?, ?, ?, ?, ?)",
            defaults,
        )

    # Prize wall items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rumble_prizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cost INTEGER NOT NULL DEFAULT 0,
            stock INTEGER,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Seed default prizes if empty
    cursor.execute("SELECT COUNT(*) FROM rumble_prizes")
    if cursor.fetchone()[0] == 0:
        default_prizes = [
            ("TTS for a reluctant friend", 0, None, "TTS purchased for a friend who is reluctant to play because they don't want to buy TTS", 1, 1),
            ("Clown Emoji", 0, 10, None, 2, 1),
            ("Lester Crayon Drawing Alt Art Proxy", 0, None, "Lester crayon drawing alternate art proxy of any avatar (costs clown emojis)", 3, 1),
            ("Foil Ordinary", 0, None, None, 10, 1),
            ("Foil Exceptional", 0, None, None, 11, 1),
            ("Foil Elite", 0, None, None, 12, 1),
            ("Foil Unique", 0, None, None, 13, 1),
        ]
        cursor.executemany(
            "INSERT INTO rumble_prizes (name, cost, stock, description, sort_order, active) VALUES (?, ?, ?, ?, ?, ?)",
            default_prizes,
        )

    # Prize redemption history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rumble_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_user_id TEXT NOT NULL,
            prize_id INTEGER NOT NULL REFERENCES rumble_prizes(id),
            cost INTEGER NOT NULL,
            admin_user_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_redemptions_user
        ON rumble_redemptions(discord_user_id)
    """)

    conn.commit()
    conn.close()
    logger.info("rumble tables ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    create_rumble_tables()
    logger.info("Migration completed.")
