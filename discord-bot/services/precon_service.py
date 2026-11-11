"""Bot-side access to the precon (Lavamancer vs Frostmage) ladder in match_records.db."""

import contextlib
import logging
import sqlite3
import time

from services import precon_ladder

logger = logging.getLogger("discord_bot")

MATCH_RECORDS_DB = "match_records.db"
PRECON_QUEUE = "precon"
# Status polls (Discord and Play Sorcery Online) ask whether the queue is open
# many times a minute; one lookup a minute is plenty.
_OPEN_CACHE_SECONDS = 60
_open_cache = {"at": 0.0, "season": None}
_settings_cache = {"at": 0.0, "settings": None}


@contextlib.contextmanager
def connect():
    conn = sqlite3.connect(MATCH_RECORDS_DB, timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def clear_cache():
    """Forget the cached season and settings (the Admin page asks for this after a change)."""
    _open_cache["at"] = 0.0
    _open_cache["season"] = None
    _settings_cache["at"] = 0.0
    _settings_cache["settings"] = None


def settings(use_cache=True) -> dict:
    """The precon rules (queue switch, games to be ranked, rematch block, season length)."""
    now = time.monotonic()
    if use_cache and _settings_cache["settings"] is not None and now - _settings_cache["at"] < _OPEN_CACHE_SECONDS:
        return _settings_cache["settings"]
    try:
        with connect() as conn:
            current = precon_ladder.get_settings(conn)
    except sqlite3.Error:
        logger.error("Could not read precon settings", exc_info=True)
        current = {name: spec[0] for name, spec in precon_ladder.SETTINGS.items()}
    _settings_cache["at"] = now
    _settings_cache["settings"] = current
    return current


def update_settings(changes, updated_by=None) -> dict:
    with connect() as conn:
        current = precon_ladder.update_settings(conn, changes, updated_by=updated_by)
    clear_cache()
    return current


def queue_is_open() -> bool:
    """The precon queue shows only when an admin has switched it on AND a season is running."""
    return bool(settings().get("queue_enabled")) and season_is_open()


def open_season(use_cache=True):
    """The precon season open right now, or None."""
    now = time.monotonic()
    if use_cache and _open_cache["at"] and now - _open_cache["at"] < _OPEN_CACHE_SECONDS:
        return _open_cache["season"]
    try:
        with connect() as conn:
            season = precon_ladder.open_season(conn)
    except sqlite3.Error:
        logger.error("Could not read the precon season", exc_info=True)
        season = None
    _open_cache["at"] = now
    _open_cache["season"] = season
    return season


def season_is_open() -> bool:
    return open_season() is not None


def start_season(name, created_by=None, days=None):
    if days is None:
        days = settings(use_cache=False)["season_days"]
    with connect() as conn:
        season = precon_ladder.start_season(conn, name, created_by=created_by, days=days)
    clear_cache()
    return season


def end_season():
    with connect() as conn:
        season = precon_ladder.end_season(conn)
    clear_cache()
    return season


def seasons_needing_final_post():
    with connect() as conn:
        return precon_ladder.seasons_needing_final_post(conn)


def mark_final_posted(season_id):
    with connect() as conn:
        precon_ladder.mark_final_posted(conn, season_id)


def record_match(**kwargs):
    with connect() as conn:
        return precon_ladder.record_match(conn, **kwargs)


def match_for_pairing(pairing_id):
    with connect() as conn:
        return precon_ladder.match_for_pairing(conn, pairing_id)


def remove_match(match_id):
    with connect() as conn:
        return precon_ladder.remove_match(conn, match_id)


def played_last_game_together(player_a, player_b) -> bool:
    if not settings().get("block_rematch", True):
        return False
    try:
        with connect() as conn:
            return precon_ladder.played_last_game_together(conn, player_a, player_b)
    except sqlite3.Error:
        logger.error("Could not check precon rematch", exc_info=True)
        return False


def current_or_latest_season():
    with connect() as conn:
        return precon_ladder.current_or_latest_season(conn)


def standings(season_id):
    with connect() as conn:
        return precon_ladder.standings(conn, season_id)


def player_standing(season_id, user_id):
    with connect() as conn:
        return precon_ladder.player_standing(conn, season_id, user_id)


def season_stats(season_id):
    with connect() as conn:
        return precon_ladder.season_stats(conn, season_id)


def rating_change_text(result, winner_name, loser_name) -> str:
    """' *(LM/FM ladder: A 1500→1562, B 1500→1438)*' or the unrated note."""
    if not result.get("rated"):
        return " *(Precon match - no precon season is running, so the ladder didn't move)*"
    return (
        f" *(LM/FM ladder: {winner_name} {result['winner_before']}→{result['winner_after']}, "
        f"{loser_name} {result['loser_before']}→{result['loser_after']})*"
    )
