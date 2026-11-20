"""Provisional Glicko-2 ratings in Discord messages.

A Glicko-2 rating swings a lot over its first games, so until it has
PROVISIONAL_GAMES games it is shown as "Provisional (n/8)" instead of a
number, and the change from each of those games is never shown. Ranked lists
put settled entries first (they alone take rank numbers), then provisional
ones. Elo ladders are shown as before.

The rule itself (``is_provisional``, ``change_hidden``, ``provisional_label``)
lives in services/glicko2_season.py; this module only applies it to the
bot's displays.
"""

from __future__ import annotations

import sqlite3

from services import glicko2_season as g2

PROVISIONAL_GAMES = g2.PROVISIONAL_GAMES
provisional_label = g2.provisional_label
is_provisional = g2.is_provisional


def rating_text(rating, games, glicko2: bool) -> str:
    """The rating as shown: the number, or "Provisional (n/8)"."""
    if glicko2 and g2.is_provisional(games):
        return g2.provisional_label(games)
    return str(rating)


def change_text(change, games_after, unit: str = "") -> str | None:
    """A per-match change like "+12 ELO", or None when it is hidden."""
    if change is None or g2.change_hidden(games_after):
        return None
    return f"{change:+d}{unit}"


def settled_first(entries, glicko2: bool, games, name) -> list[tuple[int | None, object]]:
    """(rank, entry) pairs: settled entries ranked in the given order, then provisional ones.

    ``entries`` is the ladder best first; ``games`` and ``name`` read an
    entry's game count and name. Provisional entries get rank None and are
    listed by games played (most first), then name. Elo ladders: every entry
    keeps its position.
    """
    entries = list(entries)
    if not glicko2:
        return list(enumerate(entries, start=1))
    settled = [e for e in entries if not g2.is_provisional(games(e))]
    pending = sorted(
        (e for e in entries if g2.is_provisional(games(e))),
        key=lambda e: (-(games(e) or 0), str(name(e) or "").lower()),
    )
    return [*enumerate(settled, start=1), *((None, e) for e in pending)]


def _active_event():
    from repositories.elo_repo import get_active_event

    return get_active_event()


def season_games(user_id, avatar=None, event=None, elo_db: str = "elo.db") -> int:
    """Games on the entry a match uses: the avatar entry in Avatar mode, else the player's."""
    conn = sqlite3.connect(elo_db)
    try:
        if avatar and event and event.get("elo_mode") == "avatar":
            row = conn.execute(
                "SELECT games_played FROM event_avatar_standings "
                "WHERE event_id = ? AND user_id = ? AND avatar = ?",
                (event["event_id"], user_id, avatar),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT online_event_games FROM overall_standings WHERE user_id = ?", (user_id,)
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        conn.close()
    return (row[0] or 0) if row else 0


def entry_provisional(user_id, avatar=None, event=None) -> bool:
    """Whether this player's (or avatar entry's) season rating is still provisional."""
    event = event if event is not None else _active_event()
    if not g2.is_glicko2(event):
        return False
    return g2.is_provisional(season_games(user_id, avatar, event))


def season_rating_text(user_id, rating, avatar=None, event=None) -> str:
    """A season rating as shown, looked up for one player (or avatar entry)."""
    event = event if event is not None else _active_event()
    if not g2.is_glicko2(event):
        return str(rating)
    return rating_text(rating, season_games(user_id, avatar, event), True)


def lifetime_is_glicko2(elo_db: str = "elo.db") -> bool:
    conn = sqlite3.connect(elo_db)
    try:
        return g2.lifetime_is_glicko2(conn)
    finally:
        conn.close()


def lifetime_games(user_ids=None, elo_db: str = "elo.db") -> dict[int, int]:
    """Glicko-2 lifetime games per player (all players, or the given ones)."""
    conn = sqlite3.connect(elo_db)
    try:
        rows = conn.execute("SELECT user_id, COALESCE(online_games, 0) FROM overall_standings").fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    games = dict(rows)
    if user_ids is not None:
        return {uid: games.get(uid, 0) for uid in user_ids}
    return games


def corrected_side_text(result: dict, side: str) -> str:
    """'**Name** (+12 ELO)' for a correct_match_record result; no number if hidden."""
    name = result[f"new_{side}_name"]
    if result.get(f"new_{side}_elo_change_hidden"):
        return f"**{name}**"
    return f"**{name}** ({result[f'new_{side}_elo_change']:+d} ELO)"
