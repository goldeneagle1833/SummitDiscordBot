"""Data access layer for the card_points and points_config tables in elo.db."""

import sqlite3


def get_all_card_points() -> dict[str, int]:
    """Return a dict mapping card_name (lowercase) -> point_value."""
    conn = sqlite3.connect("elo.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT card_name, point_value FROM card_points")
        result = {row[0].lower(): row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        result = {}
    conn.close()
    return result


def get_max_budget() -> int:
    """Get the max point budget for decks."""
    conn = sqlite3.connect("elo.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM points_config WHERE key = 'max_budget'")
        row = cursor.fetchone()
        result = int(row[0]) if row else 50
    except sqlite3.OperationalError:
        result = 50
    conn.close()
    return result
