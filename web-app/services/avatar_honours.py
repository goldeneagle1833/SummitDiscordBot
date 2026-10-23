"""Season avatar honours: the top three on each avatar's ladder, per ended Avatar-mode season.

An Avatar-mode season rates every player/avatar pair on its own Elo ladder
(event_avatar_standings). Those entries stay in place when the season is
archived, so once it ends, the first three entries on each avatar with at
least 10 games earn "Gothic Season 9 Top Imposter", "... 2nd Imposter" and
"... 3rd Imposter". Each player counts only on their highest-ranked avatar
(10+ games) that season, so they hold at most one honour per season. Player-mode seasons have no per-avatar ladder and earn
none.

Nothing is stored: like the bracket marks, honours are read from the data
they come from, so a season earns its honours the moment it is archived.
The running season never earns any.
"""

import logging
import os
import sqlite3
import threading

import webapp_config
from repositories.elo import EloRepository

logger = logging.getLogger(__name__)

HONOUR_PLACES = 3
HONOUR_MIN_GAMES = 10
PLACE_WORDS = {1: "Top", 2: "2nd", 3: "3rd"}

_cache = {}
_cache_lock = threading.Lock()


def honour_label(place: int, avatar: str) -> str:
    """'Top Imposter', '2nd Imposter', '3rd Imposter'."""
    return f"{PLACE_WORDS[place]} {avatar}"


def _db_signature() -> tuple:
    """Changes whenever elo.db or match_records.db (or their WAL files) are written."""
    parts = []
    for path in (webapp_config.ELO_DB_PATH, webapp_config.MATCH_RECORDS_DB_PATH):
        for suffix in ("", "-wal"):
            try:
                st = os.stat(f"{path}{suffix}")
                parts.append((str(path), suffix, st.st_mtime_ns, st.st_size))
            except OSError:
                parts.append((str(path), suffix, None))
    return tuple(parts)


def _ended_avatar_seasons() -> list[dict]:
    """Ended Avatar-mode seasons, oldest first."""
    conn = sqlite3.connect(str(webapp_config.ELO_DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(events)")
        if "elo_mode" not in {r[1] for r in cur.fetchall()}:
            return []
        cur.execute(
            """SELECT event_id, event_name, end_date FROM events
               WHERE elo_mode = 'avatar' AND is_active = 0 AND end_date IS NOT NULL
               ORDER BY start_date ASC, event_id ASC"""
        )
        return [{"id": r[0], "name": r[1], "end_date": r[2]} for r in cur.fetchall()]
    finally:
        conn.close()


def _season_records(event_id: int) -> dict:
    """{(user_id, avatar): {wins, losses}} from the season's archived avatar games."""
    conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(match_records_archive)")
        columns = {r[1] for r in cur.fetchall()}
        if not {"event_id", "winner_avatar", "loser_avatar"} <= columns:
            return {}
        # Bracket games move lifetime Elo only, never the season ladder
        not_bracket = " AND (source IS NULL OR source != 'Bracket')" if "source" in columns else ""
        cur.execute(
            f"""SELECT user_id, avatar, SUM(wins), SUM(losses) FROM (
                    SELECT winner_id AS user_id, winner_avatar AS avatar, 1 AS wins, 0 AS losses
                    FROM match_records_archive
                    WHERE event_id = ? AND winner_avatar IS NOT NULL {not_bracket}
                    UNION ALL
                    SELECT losser_id AS user_id, loser_avatar AS avatar, 0 AS wins, 1 AS losses
                    FROM match_records_archive
                    WHERE event_id = ? AND loser_avatar IS NOT NULL {not_bracket}
                ) GROUP BY user_id, avatar""",
            (event_id, event_id),
        )
        return {
            (str(r[0]), r[1]): {"wins": int(r[2]), "losses": int(r[3])} for r in cur.fetchall()
        }
    finally:
        conn.close()


def _custom_names() -> dict:
    try:
        from repositories.user_profiles import UserProfileRepository

        return UserProfileRepository().get_all_custom_display_names()
    except Exception:
        return {}


def _season_honours(season: dict, names: dict) -> list[dict]:
    """Top three per avatar on the season's ladder (event Elo, 10+ games).

    A player counts once per season, on their highest-ranked avatar: their
    other avatar entries step aside, so the next player on that avatar moves up.
    """
    records = _season_records(season["id"])
    ladders = {}
    placed = set()
    # Already best first: event Elo, then games played
    for entry in EloRepository(webapp_config.ELO_DB_PATH).get_avatar_standings(season["id"]):
        user_id = str(entry["user_id"])
        record = records.get((user_id, entry["avatar"]))
        games = entry["games_played"]
        if games < HONOUR_MIN_GAMES or user_id in placed:
            continue
        placed.add(user_id)
        ladders.setdefault(entry["avatar"], []).append(
            {
                "player_id": user_id,
                "name": names.get(user_id) or entry["display_name"] or f"Player {user_id}",
                "elo": entry["event_elo"],
                "games": games,
                "wins": record["wins"] if record else None,
                "losses": record["losses"] if record else None,
            }
        )

    honours = []
    for avatar, entries in sorted(ladders.items()):
        for place, player in enumerate(entries[:HONOUR_PLACES], start=1):
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
    """Every honour from every ended Avatar-mode season, newest season first."""
    key = _db_signature()
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    honours = []
    try:
        seasons = _ended_avatar_seasons()
    except sqlite3.OperationalError as e:
        logger.warning("Could not list seasons for avatar honours: %s", e)
        seasons = []
    names = _custom_names() if seasons else {}
    for season in reversed(seasons):
        try:
            honours.extend(_season_honours(season, names))
        except sqlite3.OperationalError as e:
            logger.warning("Could not read avatar honours for %s: %s", season["name"], e)

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
