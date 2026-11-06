"""Provisional Glicko-2 ratings on the site.

A Glicko-2 rating swings a lot over its first games, so until an entry has
PROVISIONAL_GAMES games its rating is not shown ("Provisional (n/8)"), it takes
no rank, and the per-match changes made while it settled stay hidden (changes
show from the game after it settles). Elo ladders are never affected.

JSON contract (shared with the React app):
- A provisional rating is ``null`` and its object carries ``provisional: true``
  and ``provisional_games: n`` (objects holding several ratings use prefixed
  names, e.g. ``event_provisional`` / ``event_provisional_games``). Settled
  Glicko-2 entries carry ``provisional: false``. Rank fields are ``null`` for
  provisional entries, and settled entries rank among settled entries only.
- A hidden per-match change is ``null`` with a sibling ``<field>_hidden: true``.
"""

import sqlite3

import webapp_config
from services import glicko2_season as g2

NEEDED = g2.PROVISIONAL_GAMES
is_provisional = g2.is_provisional
change_hidden = g2.change_hidden

# Each side's game count after the match (Glicko-2 rows only; NULL otherwise)
GAMES_COLUMNS = (
    "winner_event_games", "loser_event_games",
    "winner_avatar_games", "loser_avatar_games",
    "winner_lifetime_games", "loser_lifetime_games",
)

# Per-match change (or "after") field -> the games column that decides it
CHANGE_GAMES = {
    "winner_elo_change": "winner_event_games",
    "loser_elo_change": "loser_event_games",
    "winner_avatar_elo_change": "winner_avatar_games",
    "loser_avatar_elo_change": "loser_avatar_games",
    "winner_avatar_elo_after": "winner_avatar_games",
    "loser_avatar_elo_after": "loser_avatar_games",
    "winner_lifetime_elo_change": "winner_lifetime_games",
    "loser_lifetime_elo_change": "loser_lifetime_games",
    "winner_lifetime_elo_after": "winner_lifetime_games",
    "loser_lifetime_elo_after": "loser_lifetime_games",
}


# --- SQL ---------------------------------------------------------------------

def games_select(columns, alias: str = "") -> str:
    """SELECT fragment for the games columns, NULL where the table lacks one."""
    prefix = f"{alias}." if alias else ""
    return ", ".join(
        f"{prefix}{col}" if col in columns else f"NULL AS {col}" for col in GAMES_COLUMNS
    )


def table_games_select(conn, table: str, alias: str = "") -> str:
    """games_select for a table (``conn`` may be a connection or a cursor)."""
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return games_select(columns, alias)


def event_games_select(conn, table: str) -> str:
    """Just ``winner_event_games, loser_event_games`` (NULLs when the table lacks them)."""
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if {"winner_event_games", "loser_event_games"} <= columns:
        return "winner_event_games, loser_event_games"
    return "NULL, NULL"


def mask_pair(match: dict, winner_games, loser_games,
              fields=("winner_elo_change", "loser_elo_change")) -> dict:
    """Null a winner/loser change pair where that side was provisional, adding ``<field>_hidden``."""
    for field, games in zip(fields, (winner_games, loser_games)):
        if change_hidden(games):
            match[field] = None
            match[f"{field}_hidden"] = True
    return match


# --- Per-match changes -------------------------------------------------------

def mask_match(row: dict, fields=None) -> dict:
    """Null each change field made while its side was provisional, adding ``<field>_hidden``.

    Works in place on a dict holding the change fields and their games
    columns (see CHANGE_GAMES); fields whose games column is missing or NULL
    (Elo rows) are left alone. Returns the row.
    """
    for field in fields or CHANGE_GAMES:
        if field in row and change_hidden(row.get(CHANGE_GAMES[field])):
            row[field] = None
            row[f"{field}_hidden"] = True
    return row


def side_change(row: dict, did_win: bool, change="elo_change", games="event_games"):
    """(change, hidden) for one side of a match dict."""
    side = "winner" if did_win else "loser"
    if change_hidden(row.get(f"{side}_{games}")):
        return None, True
    return row.get(f"{side}_{change}"), False


# --- Ratings and rankings ----------------------------------------------------

def mark(obj: dict, games, value_keys=(), rank_keys=(), prefix: str = "") -> bool:
    """Flag a Glicko-2 rating object; null its value and rank fields while provisional.

    Adds ``<prefix>provisional`` and ``<prefix>provisional_games``. Returns
    whether it is provisional.
    """
    provisional = is_provisional(games)
    obj[f"{prefix}provisional"] = provisional
    obj[f"{prefix}provisional_games"] = int(games or 0)
    if provisional:
        for key in (*value_keys, *rank_keys):
            if key in obj:
                obj[key] = None
    return provisional


def rank_settled_first(rows: list, value_key: str, name_key: str = "name",
                       rank_key: str | None = "rank") -> list:
    """Settled rows by rating (best first), then provisional rows by games, then name.

    Rows must already be marked (see ``mark``). Settled rows are numbered
    1..n in ``rank_key``; provisional rows get ``None``. Returns a new list.
    """
    settled = [r for r in rows if not r.get("provisional")]
    pending = [r for r in rows if r.get("provisional")]
    settled.sort(key=lambda r: r.get(value_key) or 0, reverse=True)
    pending.sort(key=lambda r: (-(r.get("provisional_games") or 0),
                                str(r.get(name_key) or "").casefold()))
    if rank_key:
        for rank, row in enumerate(settled, 1):
            row[rank_key] = rank
        for row in pending:
            row[rank_key] = None
    return settled + pending


# --- Ladder state from elo.db ------------------------------------------------

def _elo_conn(elo_db_path=None):
    return sqlite3.connect(str(elo_db_path or webapp_config.ELO_DB_PATH))


def _columns(conn, table) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def active_event(elo_db_path=None) -> dict | None:
    conn = _elo_conn(elo_db_path)
    try:
        return g2.get_event(conn)
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def event_is_glicko2(event_id=None, elo_db_path=None) -> bool:
    """Whether an event (the active one by default) runs on Glicko-2."""
    conn = _elo_conn(elo_db_path)
    try:
        return g2.is_glicko2(g2.get_event(conn, event_id))
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def lifetime_is_glicko2(elo_db_path=None) -> bool:
    conn = _elo_conn(elo_db_path)
    try:
        return g2.lifetime_is_glicko2(conn)
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def standings_games(elo_db_path=None) -> dict:
    """{user_id (str): (season games, lifetime games)} from overall_standings."""
    conn = _elo_conn(elo_db_path)
    try:
        cols = _columns(conn, "overall_standings")
        event = "online_event_games" if "online_event_games" in cols else "0"
        lifetime = "online_games" if "online_games" in cols else "0"
        return {
            str(uid): (ev or 0, life or 0)
            for uid, ev, life in conn.execute(
                f"SELECT user_id, {event}, {lifetime} FROM overall_standings"
            )
        }
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def archived_season_games(event_id, elo_db_path=None, match_db_path=None) -> dict | None:
    """{user_id (str): rated games} for a Glicko-2 event, or None for an Elo event.

    Ended Glicko-2 seasons keep their matches (tagged with the event), so the
    count comes from the same rows the season was rated from.
    """
    conn = _elo_conn(elo_db_path)
    try:
        event = g2.get_event(conn, event_id)
    except sqlite3.OperationalError:
        event = None
    finally:
        conn.close()
    if not g2.is_glicko2(event):
        return None
    match_conn = sqlite3.connect(str(match_db_path or webapp_config.MATCH_RECORDS_DB_PATH))
    try:
        matches = g2.season_matches(match_conn, event)
    except sqlite3.OperationalError:
        matches = []
    finally:
        match_conn.close()
    games: dict[str, int] = {}
    for m in matches:
        for uid in (m["winner_id"], m["losser_id"]):
            games[str(uid)] = games.get(str(uid), 0) + 1
    return games


def archived_ladder(event_id, elo_db_path=None, match_db_path=None) -> list | None:
    """An ended Glicko-2 season's archived ladder with provisional entries marked.

    Ratings of players short of the minimum are hidden and the rest are
    ranked among themselves (game counts come from the season's matches).
    None for Elo seasons.
    """
    from repositories.elo import EloRepository

    games = archived_season_games(event_id, elo_db_path, match_db_path)
    if games is None:
        return None
    rows = EloRepository(elo_db_path or webapp_config.ELO_DB_PATH).get_archived_event_leaderboard(event_id)
    for row in rows:
        mark(row, games.get(str(row["user_id"]), 0), value_keys=("event_elo",))
    return rank_settled_first(rows, "event_elo", name_key="display_name")


def settled_rank(rating, rating_column: str, games_column: str, elo_db_path=None):
    """1 + settled players rated above ``rating`` on an overall_standings ladder."""
    conn = _elo_conn(elo_db_path)
    try:
        return conn.execute(
            f"SELECT COUNT(*) FROM overall_standings WHERE {rating_column} > ? "
            f"AND COALESCE({games_column}, 0) >= ?",
            (rating, NEEDED),
        ).fetchone()[0] + 1
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def legacy_elo(user_id, elo_db_path=None):
    """The frozen Seasons 1-8 lifetime ELO (None when absent)."""
    conn = _elo_conn(elo_db_path)
    try:
        if "legacy_online_elo" not in _columns(conn, "overall_standings"):
            return None
        row = conn.execute(
            "SELECT legacy_online_elo FROM overall_standings WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
