"""Season avatar honours: the top three players on each avatar, per ended season.

When a season is archived, its games sit in match_records_archive under the
season's event_id. The Top Players by Avatar page ranks each avatar's players
for that season by Avatar Score, with a 10-game minimum; the first three on
each list earn "Gothic Season 7 Top Imposter", "... 2nd Imposter" and
"... 3rd Imposter".

Nothing is stored: like the bracket marks, honours are read from the data
they come from, so every season archived before this existed is covered and
a season earns its honours the moment it is archived. The running season
never earns any.
"""

import logging
import sqlite3
import threading

logger = logging.getLogger(__name__)

HONOUR_PLACES = 3
HONOUR_MIN_GAMES = 10
PLACE_WORDS = {1: "Top", 2: "2nd", 3: "3rd"}

_cache = {}
_cache_lock = threading.Lock()


def honour_label(place: int, avatar: str) -> str:
    """'Top Imposter', '2nd Imposter', '3rd Imposter'."""
    return f"{PLACE_WORDS[place]} {avatar}"


def _ended_seasons() -> list[dict]:
    from routes.api.avatars import _get_all_seasons

    return [s for s in _get_all_seasons() if not s["is_active"] and s.get("end_date")]


def _season_tally(season_id) -> dict:
    """{avatar: {player_id: {wins, losses, name}}} for one ended season.

    The same rows the Top Players by Avatar page reads for that season
    (online games reported through the Summit).
    """
    import routes.api.avatars as avatars

    if not avatars.MATCH_RECORDS_DB_PATH.exists():
        return {}
    conn = sqlite3.connect(str(avatars.MATCH_RECORDS_DB_PATH))
    try:
        rows, use_new_columns = avatars._collect_discord_rows_with_players(conn.cursor(), season_id)
        players = {}
        avatars._tally_avatar_stats_with_players(rows, use_new_columns, {}, players)
        return players
    finally:
        conn.close()


def _season_honours(season: dict) -> list[dict]:
    from routes.api.avatars import calculate_avatar_score

    honours = []
    for avatar, players in _season_tally(season["id"]).items():
        ranked = []
        for player_id, stats in players.items():
            total = stats["wins"] + stats["losses"]
            if total < HONOUR_MIN_GAMES:
                continue
            ranked.append(
                {
                    "player_id": str(player_id),
                    "name": stats["name"] or f"Player {player_id}",
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "games": total,
                    "win_rate": round(stats["wins"] / total * 100, 1),
                    "avatar_score": calculate_avatar_score(stats["wins"], stats["losses"]),
                }
            )
        # Same order as the Top Players page
        ranked.sort(
            key=lambda p: (p["avatar_score"], p["win_rate"], p["wins"], p["games"]),
            reverse=True,
        )
        for place, player in enumerate(ranked[:HONOUR_PLACES], start=1):
            label = honour_label(place, avatar)
            honours.append(
                {
                    **player,
                    "season_id": season["id"],
                    "season": season["name"],
                    "season_ended": season["end_date"],
                    "avatar": avatar,
                    "place": place,
                    "label": label,
                    "title": f"{season['name']} {label}",
                }
            )
    return honours


def get_all_honours() -> list[dict]:
    """Every honour from every ended season, newest season first."""
    import routes.api.avatars as avatars

    seasons = _ended_seasons()
    key = (
        tuple((s["id"], s["name"], s["end_date"]) for s in seasons),
        avatars._match_db_signature(),
    )
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    honours = []
    for season in reversed(seasons):
        try:
            season_honours = _season_honours(season)
        except sqlite3.OperationalError as e:
            logger.warning("Could not read avatar honours for %s: %s", season["name"], e)
            continue
        season_honours.sort(key=lambda h: (h["avatar"], h["place"]))
        honours.extend(season_honours)

    with _cache_lock:
        _cache.clear()
        _cache[key] = honours
    return honours


def get_honours_by_player() -> dict:
    """{player_id: [honour, ...]}, each player's newest season first."""
    by_player = {}
    for honour in get_all_honours():
        by_player.setdefault(honour["player_id"], []).append(honour)
    return by_player


def reset_cache():
    with _cache_lock:
        _cache.clear()
