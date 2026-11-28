"""Open API: one player's ranked match history (GET /api/public/players/<id>/matches).

Per match it gives the result, the opponent, the date, play or draw, the game
length, the rating change the profile shows, and each side's avatar and deck
elements. Never a deck list, a deck link, a snapshot or a replay (Bruce: avatar
and elements only).

Rules it follows, the same as the player's profile for a logged-out visitor:
- ranked Discord games only (casual, testing, solo reports, Limited and paper
  are left out);
- a player who reset their profile shows nothing before the reset (or before
  the current season started, if that is earlier);
- a rating change made while that player was provisional (Glicko-2) is null;
- match ids are the site's own: live table rowids, archived games + 1e9.

Avatar and elements of games newer than the latest Meta Report batch release
(1st/15th) are held back (null, ``deck_info_released: false``), so the API
can't be used to rebuild the meta before it is published.

Everything is read from Summit's own database (never Play Sorcery Online), and
each player's list is cached for a minute.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import OrderedDict

import webapp_config
from services import data_release, provisional
from services.avatar_elo import get_player_avatar_changes
from utils.match_tables import live_matches

ARCHIVE_TABLE = "match_records_archive"
ARCHIVE_ID_OFFSET = 1_000_000_000
NON_RANKED_TYPES = ("casual", "testing")
ELEMENTS = ("Air", "Earth", "Fire", "Water")

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100
CACHE_SECONDS = 60
_CACHE_MAX = 500
TERMS_URL = "https://sorcererssummit.com/data-terms"

_cache: "OrderedDict[tuple, tuple[float, dict]]" = OrderedDict()
_cache_lock = threading.Lock()


class PlayerNotFound(Exception):
    pass


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def normalize_player_id(raw: str) -> str:
    """Bare numeric id (Discord ID, or a Google id with ``google_`` stripped)."""
    value = (raw or "").strip()
    if value.startswith("google_"):
        from services.summit_player_numbers import bot_player_id
        value = bot_player_id(value)
    if not value.isdigit() or len(value) > 30:
        raise ValueError("player_id must be a Discord ID (digits only)")
    return value


def deck_info(deck_json) -> tuple[str | None, list[str]]:
    """(avatar, sorted elements) from a stored deck. Nothing else leaves this function."""
    if not deck_json or deck_json in ("{}", ""):
        return None, []
    try:
        deck = json.loads(deck_json)
    except (TypeError, ValueError):
        return None, []
    if not isinstance(deck, dict):
        return None, []
    avatar = None
    avatars = deck.get("avatar") or []
    if isinstance(avatars, list):
        for card in avatars:
            if isinstance(card, dict) and card.get("name") and card.get("type") == "Avatar":
                avatar = card["name"]
                break
        if not avatar and avatars and isinstance(avatars[0], dict):
            avatar = avatars[0].get("name") or None
    found = set()
    for section in ("spellbook", "sideboard"):
        cards = deck.get(section) or []
        if not isinstance(cards, list):
            continue
        for card in cards:
            if not isinstance(card, dict):
                continue
            for element in str(card.get("elements") or "").split(","):
                if element.strip() in ELEMENTS:
                    found.add(element.strip())
    return avatar, sorted(found)


def _columns(conn, table) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _seasons(elo_db) -> tuple[dict[int, str], int | None, dict[int, tuple]]:
    """({event_id: name}, active event id, {event_id: (start, end)})."""
    names, windows, active = {}, {}, None
    try:
        conn = sqlite3.connect(str(elo_db))
        try:
            for event_id, name, start, end, is_active in conn.execute(
                "SELECT event_id, event_name, start_date, end_date, is_active FROM events"
            ):
                names[int(event_id)] = name
                windows[int(event_id)] = (start, end)
                if is_active:
                    active = int(event_id)
        finally:
            conn.close()
    except sqlite3.OperationalError:
        pass
    return names, active, windows


def _select(cols: set[str], table: str, id_expr: str) -> str:
    def col(name):
        return name if name in cols else f"NULL AS {name}"

    return f"""
        SELECT {id_expr} AS match_id, timestamp, winner_id, losser_id,
               winner_display_name, losser_display_name,
               winner_elo_change, loser_elo_change,
               {col('json_deck_data_winner')}, {col('json_deck_data_loser')},
               {col('winner_went_first')}, {col('loser_went_first')}, first_player,
               match_time, {col('match_type')}, {col('event_id')},
               {col('winner_event_games')}, {col('loser_event_games')}
          FROM {table}
         WHERE (winner_id = ? OR losser_id = ?)
    """


def _on_play(did_win, winner_first, loser_first, first_player):
    """True on the play, False on the draw, None when never recorded (profile rule)."""
    if winner_first is not None or loser_first is not None:
        went_first = winner_first if did_win else loser_first
        if not went_first:
            return None
        return "y" in str(went_first).lower()
    if not first_player:
        return None
    return bool(did_win) if "y" in str(first_player).lower() else not did_win


def _reset_cutoff(player_id: str, active_start: str | None) -> str | None:
    """Games before this are hidden from visitors (the player reset their profile)."""
    try:
        from repositories.user_profiles import UserProfileRepository

        repo = UserProfileRepository()
        reset_at = repo.get_profile_reset_at(player_id) or repo.get_profile_reset_at(f"google_{player_id}")
    except Exception:
        return None
    if not reset_at:
        return None
    return min(str(reset_at), str(active_start)) if active_start else str(reset_at)


def _load_rows(player_id: str, match_db) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(match_db))
    conn.row_factory = sqlite3.Row
    rows = []
    try:
        live = live_matches(match_db)
        sources = [(live, "rowid")]
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (ARCHIVE_TABLE,)
        ).fetchone():
            sources.append((ARCHIVE_TABLE, f"rowid + {ARCHIVE_ID_OFFSET}"))
        for table, id_expr in sources:
            cols = _columns(conn, table)
            if not cols:
                continue
            try:
                rows.extend(conn.execute(_select(cols, table, id_expr), (player_id, player_id)).fetchall())
            except sqlite3.OperationalError:
                continue
    finally:
        conn.close()
    return rows


def _build(player_id: str, season: str, owner: bool = False) -> dict:
    """Every ranked match of the player in the season, newest first (not paged).

    ``owner``: the player is reading their own history (signed-in AI app), so
    the newest games' avatars and elements are not held back. The profile page
    already shows them to everyone; only the open API waits for the release.
    """
    elo_db = webapp_config.ELO_DB_PATH
    match_db = webapp_config.MATCH_RECORDS_DB_PATH
    names, active_id, windows = _seasons(elo_db)

    rows = _load_rows(player_id, match_db)
    if not rows:
        raise PlayerNotFound(player_id)

    active_start = windows.get(active_id, (None, None))[0] if active_id is not None else None
    cutoff = _reset_cutoff(player_id, active_start)
    release_cutoff = data_release.cutoff_timestamp()
    avatar_changes = get_player_avatar_changes(player_id, match_db)

    want_event = None
    if season == "current":
        want_event = active_id if active_id is not None else -1
    elif season != "all":
        want_event = int(season)

    player_name = None
    matches = []
    rows.sort(key=lambda r: str(r["timestamp"] or ""), reverse=True)
    for row in rows:
        if row["match_type"] in NON_RANKED_TYPES:
            continue
        ts = str(row["timestamp"] or "")
        if cutoff and ts < cutoff:
            continue
        event_id = row["event_id"]
        if event_id is None and active_id is not None:
            # The live table before Season 9 carried no event id: its games are the active season's
            event_id = active_id if row["match_id"] < ARCHIVE_ID_OFFSET else None
        if want_event is not None and event_id != want_event:
            continue

        did_win = str(row["winner_id"]) == player_id
        if player_name is None:
            player_name = row["winner_display_name"] if did_win else row["losser_display_name"]
        own_json, opp_json = (
            (row["json_deck_data_winner"], row["json_deck_data_loser"]) if did_win
            else (row["json_deck_data_loser"], row["json_deck_data_winner"])
        )

        change = row["winner_elo_change"] if did_win else row["loser_elo_change"]
        hidden = provisional.change_hidden(row["winner_event_games"] if did_win else row["loser_event_games"])
        avatar_change = avatar_changes.get((ts, str(row["winner_id"]), str(row["losser_id"])))
        if avatar_change is not None:
            change = avatar_change[0] if did_win else avatar_change[1]
            hidden = avatar_change[2] if did_win else avatar_change[3]

        released = owner or ts < release_cutoff
        if released:
            own_avatar, own_elements = deck_info(own_json)
            opp_avatar, opp_elements = deck_info(opp_json)
        else:
            own_avatar, own_elements, opp_avatar, opp_elements = None, None, None, None

        on_play = _on_play(did_win, row["winner_went_first"], row["loser_went_first"], row["first_player"])
        matches.append({
            "match_id": row["match_id"],
            "date": ts or None,
            "season_id": event_id,
            "season": names.get(event_id) if event_id is not None else None,
            "result": "win" if did_win else "loss",
            "rating_change": None if hidden else (change or 0),
            "rating_change_hidden": bool(hidden),
            "on_play": on_play,
            "match_time_minutes": row["match_time"] or None,
            "deck_info_released": released,
            "player": {"avatar": own_avatar, "elements": own_elements},
            "opponent": {
                "id": str(row["losser_id"] if did_win else row["winner_id"]),
                "name": row["losser_display_name"] if did_win else row["winner_display_name"],
                "avatar": opp_avatar,
                "elements": opp_elements,
            },
        })

    wins = sum(1 for m in matches if m["result"] == "win")
    return {
        "player": {"id": player_id, "name": player_name},
        "season": season,
        "record": {
            "wins": wins,
            "losses": len(matches) - wins,
            "games": len(matches),
            "win_rate": round(wins / len(matches) * 100, 1) if matches else None,
        },
        "deck_info_released_through": data_release.released_through().isoformat(),
        "matches": matches,
    }


def get_match_history(player_id: str, season: str = "all", page: int = 1,
                      per_page: int = DEFAULT_PER_PAGE, owner: bool = False) -> dict:
    """One page of the player's ranked history. Raises PlayerNotFound."""
    key = (player_id, season, owner)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            _cache.move_to_end(key)
            full = hit[1]
        else:
            full = None
    if full is None:
        full = _build(player_id, season, owner)
        with _cache_lock:
            _cache[key] = (now, full)
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)

    total = len(full["matches"])
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), total_pages)
    start = (page - 1) * per_page
    return {
        **{k: v for k, v in full.items() if k != "matches"},
        "terms_of_use": TERMS_URL,
        "matches": full["matches"][start:start + per_page],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_matches": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
        },
    }
