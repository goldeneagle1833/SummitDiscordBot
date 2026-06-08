"""Utility for awarding rumble bones after match confirmation.

Directly accesses the web-app's rumble.db (same server).
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("discord_bot")

# rumble.db lives in ../web-app/ relative to the discord-bot directory
_BOT_DIR = Path(__file__).parent.parent
RUMBLE_DB_PATH = _BOT_DIR.parent / "web-app" / "rumble.db"


def _connect():
    conn = sqlite3.connect(str(RUMBLE_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_earnings_config() -> dict[str, int]:
    """Return earnings config as {key: bones} dict."""
    try:
        conn = _connect()
        rows = conn.execute("SELECT key, bones FROM rumble_earnings_config").fetchall()
        conn.close()
        return {r["key"]: r["bones"] for r in rows}
    except Exception as e:
        logger.error(f"Failed to read rumble earnings config: {e}")
        return {}


def award_match_bones(winner_id: int, winner_name: str, loser_id: int, loser_name: str) -> tuple[int, int]:
    """Award bones to winner and loser after a rumble match.

    Returns (winner_bones_awarded, loser_bones_awarded).
    """
    config = get_earnings_config()
    win_bones = config.get("round_win", 3)
    loss_bones = config.get("round_loss", 1)

    if win_bones <= 0 and loss_bones <= 0:
        return (0, 0)

    try:
        conn = _connect()

        for user_id, display_name, amount, reason in [
            (str(winner_id), winner_name, win_bones, "Rumble match win"),
            (str(loser_id), loser_name, loss_bones, "Rumble match loss"),
        ]:
            if amount <= 0:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO rumble_bones (discord_user_id, display_name, balance) VALUES (?, ?, 0)",
                (user_id, display_name),
            )
            conn.execute(
                "UPDATE rumble_bones SET display_name = ?, balance = balance + ? WHERE discord_user_id = ?",
                (display_name, amount, user_id),
            )
            conn.execute(
                "INSERT INTO rumble_bone_transactions (discord_user_id, amount, reason, admin_user_id) VALUES (?, ?, ?, ?)",
                (user_id, amount, reason, None),
            )

        conn.commit()
        conn.close()
        logger.info(f"Rumble bones awarded: {winner_name} +{win_bones}, {loser_name} +{loss_bones}")
        return (win_bones, loss_bones)
    except Exception as e:
        logger.error(f"Failed to award rumble bones: {e}")
        return (0, 0)
