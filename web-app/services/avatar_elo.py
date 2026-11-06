"""A player's per-avatar event ELO for their profile (Avatar-mode events).

In an Avatar-mode event every (player, avatar) pair has its own event ELO.
The profile shows all of a player's entries with their ladder ranks, and a
graph line per avatar built from the per-avatar "ELO after" stored on each
match.
"""

from utils.match_tables import live_matches
import sqlite3
from pathlib import Path

from webapp_config import ELO_DB_PATH, MATCH_RECORDS_DB_PATH
from repositories.elo import EloRepository
from services import provisional


def _resolve_event(elo_repo: EloRepository, event_filter, archive_event_id):
    """(event_id, event_name, is_current) for the profile's event filter, or None."""
    if archive_event_id is not None:
        conn = sqlite3.connect(str(elo_repo._db_path))
        try:
            row = conn.execute(
                "SELECT event_id, event_name FROM events WHERE event_id = ?", (archive_event_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        return (row[0], row[1], False) if row else None
    if event_filter in ("current", "lifetime"):
        active = elo_repo.get_active_event()
        if active:
            return active["event_id"], active["event_name"], True
    return None


def _history(player_id, event_id, is_current, match_db_path) -> dict[str, list[dict]]:
    """{avatar: [{match_id, timestamp, elo}, ...]} oldest first.

    Points from an entry's provisional games (Glicko-2) are left out.
    """
    table, scope, params = (
        (live_matches(match_db_path), "", ())
        if is_current
        else ("match_records_archive", "AND event_id = ?", (event_id,))
    )
    id_column = "match_id" if is_current else "original_match_id"
    conn = sqlite3.connect(str(match_db_path))
    try:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "winner_avatar_elo_after" not in cols:
            return {}
        games = (
            "CASE WHEN winner_id = ? THEN winner_avatar_games ELSE loser_avatar_games END"
            if "winner_avatar_games" in cols else "NULL"
        )
        games_params = (player_id,) if "winner_avatar_games" in cols else ()
        rows = conn.execute(
            f"""SELECT {id_column}, timestamp,
                       CASE WHEN winner_id = ? THEN winner_avatar ELSE loser_avatar END,
                       CASE WHEN winner_id = ? THEN winner_avatar_elo_after ELSE loser_avatar_elo_after END,
                       {games}
                FROM {table}
                WHERE (winner_id = ? OR losser_id = ?) {scope}
                  AND winner_avatar_elo_after IS NOT NULL
                ORDER BY timestamp ASC""",
            (player_id, player_id, *games_params, player_id, player_id, *params),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()

    history: dict[str, list[dict]] = {}
    for match_id, timestamp, avatar, elo, games in rows:
        if avatar and elo is not None and not provisional.change_hidden(games):
            history.setdefault(avatar, []).append(
                {"match_id": match_id, "timestamp": timestamp, "elo": elo}
            )
    return history


def get_player_avatar_changes(player_id, match_db_path=None) -> dict:
    """{(timestamp, winner_id, loser_id): (winner_change, loser_change, winner_hidden, loser_hidden)}
    for a player's Avatar-mode matches, so match history shows the avatar entry's change.

    A change made while that side's entry was provisional (Glicko-2) is None
    with its hidden flag True.
    """
    changes = {}
    conn = sqlite3.connect(str(match_db_path or MATCH_RECORDS_DB_PATH))
    try:
        for table in ("match_records", "match_records_archive", "season_match_records"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "winner_avatar_elo_change" not in cols:
                continue
            games = (
                "winner_avatar_games, loser_avatar_games"
                if "winner_avatar_games" in cols else "NULL, NULL"
            )
            for ts, winner, loser, w_change, l_change, w_games, l_games in conn.execute(
                f"""SELECT timestamp, winner_id, losser_id, winner_avatar_elo_change,
                           loser_avatar_elo_change, {games}
                    FROM {table}
                    WHERE (winner_id = ? OR losser_id = ?) AND winner_avatar_elo_change IS NOT NULL""",
                (player_id, player_id),
            ):
                w_hidden, l_hidden = provisional.change_hidden(w_games), provisional.change_hidden(l_games)
                changes[(str(ts), str(winner), str(loser))] = (
                    None if w_hidden else w_change, None if l_hidden else l_change, w_hidden, l_hidden
                )
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()
    return changes


def get_player_avatar_elo(
    player_id,
    event_filter="current",
    archive_event_id=None,
    elo_db_path: Path | str | None = None,
    match_db_path: Path | str | None = None,
) -> dict:
    """The profile's avatar-ELO block.

    ``elo_mode`` is "player" (and ``entries`` empty) unless the event in view
    ran in Avatar mode. Lifetime view shows the running event's entries.
    """
    elo_repo = EloRepository(elo_db_path or ELO_DB_PATH)
    event = _resolve_event(elo_repo, event_filter, archive_event_id)
    if not event:
        return {"elo_mode": "player", "event_id": None, "event_name": None, "entries": [], "history": {}}
    event_id, event_name, is_current = event
    mode = elo_repo.get_event_elo_mode(event_id)
    if mode != "avatar":
        return {"elo_mode": mode, "event_id": event_id, "event_name": event_name, "entries": [], "history": {}}

    if provisional.event_is_glicko2(event_id, elo_repo._db_path):
        # Provisional entries show no rating or rank; the rest rank among settled entries
        ladder = []
        for entry in elo_repo.get_avatar_standings(event_id):
            row = dict(entry, name=entry["display_name"])
            provisional.mark(row, entry["games_played"], value_keys=("event_elo",))
            ladder.append(row)
        entries = [
            {
                "avatar": row["avatar"],
                "event_elo": row["event_elo"],
                "rank": row["rank"],
                "games_played": row["games_played"],
                "provisional": row["provisional"],
                "provisional_games": row["provisional_games"],
            }
            for row in provisional.rank_settled_first(ladder, "event_elo")
            if str(row["user_id"]) == str(player_id)
        ]
    else:
        entries = [
            {
                "avatar": entry["avatar"],
                "event_elo": entry["event_elo"],
                "rank": entry["rank"],
                "games_played": entry["games_played"],
            }
            for entry in elo_repo.get_player_avatar_standings(event_id, player_id)
        ]
    return {
        "elo_mode": "avatar",
        "event_id": event_id,
        "event_name": event_name,
        "entries": entries,
        "history": _history(player_id, event_id, is_current, match_db_path or MATCH_RECORDS_DB_PATH),
    }
