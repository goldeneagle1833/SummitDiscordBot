"""Summit player numbers: the bot-table id of a Google login.

Mirror of discord-bot/utils/player_ids.py (the two apps don't share code).
The numbers are handed out by services/summit_player_numbers.py.
"""

SUMMIT_NUMBER_MIN = 1_000_000_000_000_000
SUMMIT_NUMBER_END = 10_000_000_000_000_000  # exclusive


def is_summit_player_number(user_id) -> bool:
    """True for a Summit player number (a Google login's bot-table id)."""
    text = str(user_id if user_id is not None else "").strip()
    if not text.isdigit():
        return False
    return SUMMIT_NUMBER_MIN <= int(text) < SUMMIT_NUMBER_END
