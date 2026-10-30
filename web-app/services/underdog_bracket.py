"""The underdog bracket: the best player on each of the season's weakest avatars.

A second end-of-season bracket, separate from the ticket-holder top cut. The
season's avatars are ranked by the Avatar Score the Avatars page shows for
that season (online games only), and the 8 lowest each send their best
player, picked the way the Avatars page picks its Top Player: highest Avatar
Score with at least 10 games on that avatar.

Rules where two answers were possible:

- Bracket games are left out. They are filed under the season they followed,
  but they are not season games, so a top cut played first can't move an
  avatar into or out of the field.
- An avatar where nobody has 10 games has no player to send, so it is
  skipped and the next weakest avatar takes its place.
- One slot per player. When someone is best on more than one of the weakest
  avatars, they take the one where their Avatar Score is highest, and the
  next best player with 10 games takes the other. If that leaves an avatar
  with nobody, it drops out like one with too few games.
- Seeds go by the player's Avatar Score on their avatar, best first.
- An admin can leave avatars out (Season 8 leaves out Frostmage and
  Lavamancer); the next weakest avatars take their places.
"""

import logging
import sqlite3

import webapp_config
from utils.deck_sql import avatar_name

logger = logging.getLogger(__name__)

UNDERDOG_SIZE = 8
UNDERDOG_MIN_GAMES = 10


def _score(wins, losses):
    from routes.api.avatars import calculate_avatar_score

    return calculate_avatar_score(wins, losses)


def seasons() -> list[dict]:
    """Every season in elo.db, newest first, for the admin's season picker."""
    try:
        conn = sqlite3.connect(str(webapp_config.ELO_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT event_id, event_name, start_date, end_date, is_active FROM events"
                " ORDER BY start_date DESC, event_id DESC"
            )]
        finally:
            conn.close()
    except sqlite3.OperationalError as e:
        logger.warning("Underdog bracket: could not read events: %s", e)
        return []
    for row in rows:
        row["is_active"] = bool(row["is_active"])
    return rows


def _event(event_id) -> dict | None:
    """The season to read: an event id, "current", or None for the latest.

    With no id, the running season when there is one, otherwise the one that
    ended last.
    """
    rows = seasons()
    if event_id not in (None, "", "current"):
        try:
            event_id = int(event_id)
        except (TypeError, ValueError):
            return None
        return next((r for r in rows if r["event_id"] == event_id), None)

    active = next((r for r in rows if r["is_active"]), None)
    if active or event_id == "current":
        return active
    ended = [r for r in rows if r["end_date"]]
    return max(ended, key=lambda r: (r["end_date"], r["event_id"])) if ended else None


def _season_rows(event: dict) -> list[tuple]:
    """(winner_avatar, loser_avatar, winner_id, winner_name, loser_id, loser_name) per season game."""
    cols = (
        f"{avatar_name('json_deck_data_winner')}, {avatar_name('json_deck_data_loser')}, "
        "winner_id, winner_display_name, losser_id, losser_display_name"
    )
    conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH))
    try:
        if event["is_active"]:
            # The running season, as the Avatars page reads it.
            return conn.execute(
                f"SELECT {cols} FROM match_records WHERE source = 'Discord' OR source IS NULL"
            ).fetchall()
        return conn.execute(
            f"SELECT {cols} FROM match_records_archive"
            " WHERE event_id = ? AND COALESCE(source, '') != 'Bracket'",
            (event["event_id"],),
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("Underdog bracket: could not read matches: %s", e)
        return []
    finally:
        conn.close()


def _tally(rows):
    """Avatar records and per-avatar player records."""
    avatars, players = {}, {}
    for winner_avatar, loser_avatar, winner_id, winner_name, loser_id, loser_name in rows:
        for name, user_id, display, won in (
            (winner_avatar, winner_id, winner_name, True),
            (loser_avatar, loser_id, loser_name, False),
        ):
            if not name or name == "Unknown":
                continue
            record = avatars.setdefault(name, {"wins": 0, "losses": 0})
            record["wins" if won else "losses"] += 1
            if not user_id:
                continue
            player = players.setdefault(name, {}).setdefault(
                str(user_id), {"wins": 0, "losses": 0, "name": display or f"Player {user_id}"}
            )
            player["wins" if won else "losses"] += 1
    return avatars, players


def _ranked_players(players: dict, min_games: int) -> list[dict]:
    """Players with enough games on one avatar, best first (the Top Player order)."""
    ranked = []
    for user_id, p in players.items():
        games = p["wins"] + p["losses"]
        if games < min_games:
            continue
        ranked.append({
            "user_id": user_id,
            "display_name": p["name"],
            "wins": p["wins"],
            "losses": p["losses"],
            "games": games,
            "avatar_score": _score(p["wins"], p["losses"]),
        })
    ranked.sort(
        key=lambda p: (p["avatar_score"], p["wins"] / p["games"], p["wins"]),
        reverse=True,
    )
    return ranked


def underdog_field(event_id=None, size: int = UNDERDOG_SIZE,
                   min_games: int = UNDERDOG_MIN_GAMES, exclude=()) -> dict:
    """The season's weakest avatars and the player each one sends.

    Returns {"event", "players", "avatars"}: players in seeding order (each
    with the avatar they represent), and every avatar of the season weakest
    first with what happened to it, so the admin can see why one was skipped.
    Avatars named in ``exclude`` (any case) are listed but never picked.
    """
    left_out = {str(name).strip().lower() for name in exclude or () if str(name).strip()}
    event = _event(event_id)
    if not event:
        return {"event": None, "players": [], "avatars": [], "min_games": min_games}

    avatar_records, avatar_players = _tally(_season_rows(event))
    order = sorted(
        avatar_records.items(),
        key=lambda kv: (_score(kv[1]["wins"], kv[1]["losses"]), kv[0]),
    )

    candidates = {name: _ranked_players(avatar_players.get(name, {}), min_games) for name, _ in order}
    summary = []
    for name, record in order:
        summary.append({
            "avatar": name,
            "wins": record["wins"],
            "losses": record["losses"],
            "games": record["wins"] + record["losses"],
            "avatar_score": _score(record["wins"], record["losses"]),
            "player": None,
            "excluded": name.lower() in left_out,
            "note": (
                "Left out" if name.lower() in left_out
                else None if candidates[name]
                else f"Nobody has {min_games} games"
            ),
        })

    # Each avatar sends its best player. A player who comes out best on
    # several keeps the one where their Avatar Score is highest and steps
    # aside on the rest, where the next best player comes in. An avatar left
    # with nobody drops out and the next weakest avatar joins.
    queue = [s["avatar"] for s in summary if candidates[s["avatar"]] and not s["excluded"]]
    field, passed = [], {}  # passed: avatar -> user_ids stepping aside there
    chosen = {}
    while True:
        while len(field) < size and queue:
            field.append(queue.pop(0))
        chosen = {}
        for avatar in field:
            pick = next(
                (p for p in candidates[avatar] if p["user_id"] not in passed.get(avatar, set())), None
            )
            if pick:
                chosen[avatar] = pick
        by_player = {}
        for avatar, p in chosen.items():
            by_player.setdefault(p["user_id"], []).append(avatar)
        changed = False
        for user_id, avatars in by_player.items():
            if len(avatars) < 2:
                continue
            keep = max(avatars, key=lambda a: (chosen[a]["avatar_score"], -field.index(a)))
            for avatar in avatars:
                if avatar != keep:
                    passed.setdefault(avatar, set()).add(user_id)
                    changed = True
        empty = [a for a in field if a not in chosen]
        for avatar in empty:
            field.remove(avatar)
            changed = True
        if not changed:
            break

    by_avatar = {s["avatar"]: s for s in summary}
    for avatar in field:
        by_avatar[avatar]["player"] = chosen[avatar]
        if passed.get(avatar):
            by_avatar[avatar]["note"] = "Best player took another avatar"
    for s in summary:
        if s["player"] is None and s["note"] is None:
            s["note"] = "Its players took other avatars" if s["avatar"] in passed else "Outside the 8"

    players = sorted(
        ({**chosen[a], "avatar": a} for a in field),
        key=lambda p: (p["avatar_score"], p["wins"] / p["games"], p["wins"]),
        reverse=True,
    )
    return {
        "event": {"event_id": event["event_id"], "event_name": event["event_name"]},
        "players": players,
        "avatars": summary,
        "min_games": min_games,
    }
