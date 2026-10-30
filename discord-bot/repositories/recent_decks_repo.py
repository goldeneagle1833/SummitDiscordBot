"""A player's recently played decks, read from their Summit match history.

Same source as the profile's Recent Decks list on the website: the deck
link each player reported on their recorded matches, newest first, one entry
per deck. Only ever shown back to the player themselves (the LFG join modal).
"""

import datetime
import json
import sqlite3

from utils.avatars import avatar_from_deck
from utils.deck_checker import clean_deck_url, get_deck_id, get_pso_deck_id

RECENT_DECKS_LIMIT = 10
# Enough history to find ten distinct decks without reading every match
_ROWS_PER_TABLE = 400
_NOT_DECKS = {"No URL provided", "Admin reported match", "{}"}


def _is_deck_link(url: str) -> bool:
    if get_pso_deck_id(url):
        return True
    lowered = url.lower()
    return ("sorcerytcg.com/decks/" in lowered or "curiosa.io/decks/" in lowered) and bool(get_deck_id(url))


def _deck_name(deck_json) -> str | None:
    try:
        data = json.loads(deck_json) if deck_json else {}
    except (TypeError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return (str(name).strip() or None) if name else None


def get_recent_decks(user_id: int, limit: int = RECENT_DECKS_LIMIT) -> list[dict]:
    """The player's last ``limit`` distinct decks, newest first.

    Each entry: url, avatar, deck_name, wins, losses, last_played (ISO text).
    """
    rows = []
    conn = sqlite3.connect("match_records.db")
    try:
        cur = conn.cursor()
        for table in ("match_records", "match_records_archive"):
            try:
                cur.execute(
                    f"""
                    SELECT winner_id = ? AS did_win, timestamp,
                           COALESCE(curiosa_url_winner, curiosa_url) AS winner_url,
                           curiosa_url_loser,
                           json_deck_data_winner, json_deck_data_loser
                    FROM {table}
                    WHERE winner_id = ? OR losser_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (user_id, user_id, user_id, _ROWS_PER_TABLE),
                )
                rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                continue  # table (or a column) missing on an old database
    finally:
        conn.close()

    decks = {}
    for did_win, timestamp, winner_url, loser_url, winner_json, loser_json in rows:
        url = winner_url if did_win else loser_url
        if not url or url in _NOT_DECKS or not _is_deck_link(str(url)):
            continue
        url = clean_deck_url(str(url).strip())
        deck_json = winner_json if did_win else loser_json
        deck = decks.get(url)
        if deck is None:
            deck = decks[url] = {
                "url": url,
                "avatar": None,
                "deck_name": None,
                "wins": 0,
                "losses": 0,
                "last_played": timestamp or "",
            }
        deck["wins" if did_win else "losses"] += 1
        if timestamp and timestamp > deck["last_played"]:
            deck["last_played"] = timestamp
        # Rows come newest first, so the first readable name/avatar is the latest
        if not deck["avatar"]:
            deck["avatar"] = avatar_from_deck(deck_json)
        if not deck["deck_name"]:
            deck["deck_name"] = _deck_name(deck_json)

    ordered = sorted(decks.values(), key=lambda d: d["last_played"], reverse=True)
    return ordered[:limit]


def recent_deck_summary(deck: dict) -> str:
    """One short line for a deck's dropdown option: avatar, record, last played."""
    parts = []
    if deck.get("avatar"):
        parts.append(deck["avatar"])
    parts.append(f'{deck.get("wins", 0)}-{deck.get("losses", 0)}')
    try:
        played = datetime.datetime.fromisoformat(str(deck.get("last_played"))[:19])
        parts.append(f"last played {played:%b} {played.day}")
    except ValueError:
        pass
    return " · ".join(parts)
