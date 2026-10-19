"""One player's card stats from Sorcery Online played-card data.

PSO's result callbacks list the cards each player actually played in a game
(``sorcery_online_match_callbacks.played_cards``, keyed by player id). This
tallies only the given player's cards: how often each was played and how the
player did in the games where it was played versus the games where it was not.
"""

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def _bare(player_id) -> str:
    text = str(player_id)
    return text[7:] if text.startswith("google_") else text


QUEUE_FILTERS = ("all", "ranked", "casual")


def load_player_games(db_path, player_id, start=None, end=None, queue="all") -> list[tuple[bool, list[str]]]:
    """Return ``(won, cards_played)`` for each decided PSO game the player has card data for.

    ``queue``: 'ranked' keeps only Ranked queue games, 'casual' every other
    queue (Casual, Rumble, Limited), 'all' both.
    """
    pid = _bare(player_id)
    where = [
        "outcome = 'decided'",
        "played_cards IS NOT NULL",
        "(CAST(winner_id AS TEXT) = ? OR CAST(loser_id AS TEXT) = ?)",
    ]
    params: list = [pid, pid]
    if queue == "ranked":
        where.append("queue_type = 'ranked'")
    elif queue == "casual":
        where.append("queue_type != 'ranked'")
    if start:
        where.append("created_at >= ?")
        params.append(start)
    if end:
        where.append("created_at < ?")
        params.append(end)

    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sorcery_online_match_callbacks'"
            )
            if not cur.fetchone():
                return []
            cur.execute(
                "SELECT played_cards, winner_id FROM sorcery_online_match_callbacks"
                f" WHERE {' AND '.join(where)}",
                params,
            )
            rows = cur.fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError as e:
        logger.error("Database error loading player card stats: %s", e)
        return []

    games = []
    for played_json, winner_id in rows:
        try:
            played = json.loads(played_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(played, dict):
            continue
        cards = None
        for key, value in played.items():
            if _bare(key) == pid:
                cards = value
                break
        if not cards:
            continue
        unique = list(dict.fromkeys(c for c in cards if c))
        games.append((str(winner_id) == pid, unique))
    return games


def summarize(games: list[tuple[bool, list[str]]]) -> dict:
    """Per-card totals plus the "effect of playing it" in percentage points."""
    total = len(games)
    total_wins = sum(1 for won, _ in games if won)
    per_card: dict[str, dict] = {}
    for won, cards in games:
        for name in cards:
            stats = per_card.setdefault(name, {"games": 0, "wins": 0})
            stats["games"] += 1
            if won:
                stats["wins"] += 1

    cards = []
    for name, stats in per_card.items():
        played, wins = stats["games"], stats["wins"]
        win_rate = round(wins / played * 100, 1)
        not_played = total - played
        not_played_wins = total_wins - wins
        win_rate_not_played = round(not_played_wins / not_played * 100, 1) if not_played else None
        effect = round(win_rate - win_rate_not_played, 1) if win_rate_not_played is not None else None
        cards.append({
            "name": name,
            "games": played,
            "wins": wins,
            "losses": played - wins,
            "win_rate": win_rate,
            "win_rate_not_played": win_rate_not_played,
            "effect": effect,
        })
    cards.sort(key=lambda c: (-c["games"], c["name"]))

    return {
        "games": total,
        "wins": total_wins,
        "losses": total - total_wins,
        "win_rate": round(total_wins / total * 100, 1) if total else None,
        "unique_cards": len(cards),
        "avg_cards_per_game": round(sum(len(c) for _, c in games) / total, 1) if total else None,
        "cards": cards,
    }
