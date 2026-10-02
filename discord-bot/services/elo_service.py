"""Business logic for ELO calculations, match reporting, and event management."""

import asyncio
import sqlite3
import datetime
import json
import logging

from utils.avatars import read_deck_avatar
from utils.deck_checker import get_pso_deck_id, scrape_Curosa, scrape_curosa_async
from repositories.avatar_elo_repo import (
    AVATAR_MODE,
    ELO_MODES,
    PLAYER_MODE,
    adjust_avatar_event_elo,
    delete_player_avatar_standings,
    get_avatar_event_elo,
    get_avatar_standings,
    record_avatar_results,
)
from repositories.elo_repo import (
    create_db,
    create_events_table,
    create_match_records_archive,
    migrate_to_dual_elo_system,
    get_active_event,
    get_pairing_avatars,
    get_pairing_voice,
    AVATAR_MATCH_COLUMN_NAMES,
    ELO_COUNTING_MATCH_FILTER,
    get_total_match_count,
    update_both_player_elos,
    NON_ELO_MATCH_TYPES,
    NON_ELO_MATCH_TYPES_SQL,
)

logger = logging.getLogger("discord_bot")


# --- Pure ELO Calculations ---


def update_elo(player_elo, opponent_elo, did_win, k=32):
    """
    Calculate new Elo rating.

    :param player_elo: Current player's Elo rating
    :param opponent_elo: Opponent's Elo rating
    :param did_win: True if player won, False if lost
    :param k: K-factor (default = 32)
    :return: Updated Elo rating
    """
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0
    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)


EVENT_K_START = 16
EVENT_K_STEP = 2
EVENT_K_MAX = 32


def calculate_player_event_k(games_played: int) -> int:
    """A player's season K-factor: 16 for their first rated game of the season,
    2 more after each game, capped at 32 (reached from the 9th game)."""
    return min(EVENT_K_START + EVENT_K_STEP * max(games_played or 0, 0), EVENT_K_MAX)


def match_event_k(winner_games: int, loser_games: int) -> int:
    """The K-factor a season match is played at: the lower of the two players'."""
    return min(calculate_player_event_k(winner_games), calculate_player_event_k(loser_games))


def calculate_event_k_value(start_date):
    """
    Legacy day-based K-value (no longer used for rating: season K is now per
    player, see calculate_player_event_k). Kept for the legacy helpers below.

    Day 0: K=16, Day 1: K=18, ... Day 8+: K=32 (capped)

    Args:
        start_date: datetime when the event started

    Returns:
        int: K-value between 16 and 32
    """
    now = datetime.datetime.now()
    days_elapsed = (now - start_date).days
    k_value = 16 + (days_elapsed * 2)
    return min(k_value, 32)


# --- ELO Database Updates ---


def update_elo_db(user_id, user_display_name, did_win, opponent_id):
    """
    Update the ELO database with match results (Discord bot / online games).

    Updates both online lifetime ELO (K=32) and online event ELO (dynamic K) if an event is active.
    If no event is active, ELO is not updated (returns 0 changes).

    Returns:
        Tuple of (new_online_elo, online_change, new_online_event_elo, online_event_change, event_active)
    """
    migrate_to_dual_elo_system()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    # Check for active event
    active_event = get_active_event()

    # Get player's current online ELOs (or insert if new)
    cur.execute(
        "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id=?", (user_id,)
    )
    player_row = cur.fetchone()

    if player_row:
        player_online_elo = player_row[0] if player_row[0] else 1500
        player_online_event_elo = player_row[1] if player_row[1] else 1500
        logger.debug(
            "Existing player %s: online ELO=%d, online event ELO=%d",
            user_id, player_online_elo, player_online_event_elo,
        )
    else:
        player_online_elo = 1500
        player_online_event_elo = 1500
        cur.execute(
            """INSERT OR IGNORE INTO overall_standings
               (user_id, user_display_name, online_elo, online_event_elo) VALUES (?, ?, ?, ?)""",
            (user_id, user_display_name, player_online_elo, player_online_event_elo),
        )
        logger.debug("New player %s inserted with default online ELOs", user_id)

    # Get opponent's online ELOs (or use default if not found)
    cur.execute(
        "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id=?", (opponent_id,)
    )
    opponent_row = cur.fetchone()

    if opponent_row:
        opponent_online_elo = opponent_row[0] if opponent_row[0] else 1500
        opponent_online_event_elo = opponent_row[1] if opponent_row[1] else 1500
    else:
        opponent_online_elo = 1500
        opponent_online_event_elo = 1500

    # If no active event, don't update ELO
    if not active_event:
        logger.debug("No active event - online ELO not updated for %s", user_id)
        conn.close()
        return (player_online_elo, 0, player_online_event_elo, 0, False)

    # Calculate new online lifetime ELO (always K=32)
    new_online_elo = update_elo(
        player_online_elo, opponent_online_elo, did_win, k=32
    )
    online_change = new_online_elo - player_online_elo

    # Calculate new online event ELO (dynamic K based on days elapsed)
    event_k = calculate_event_k_value(active_event["start_date"])
    new_online_event_elo = update_elo(player_online_event_elo, opponent_online_event_elo, did_win, k=event_k)
    online_event_change = new_online_event_elo - player_online_event_elo

    logger.info(
        "Player %s online ELO updated - lifetime: %d -> %d (%+d), event (K=%d): %d -> %d (%+d)",
        user_id, player_online_elo, new_online_elo, online_change,
        event_k, player_online_event_elo, new_online_event_elo, online_event_change,
    )

    cur.execute(
        "UPDATE overall_standings SET online_elo = ?, online_event_elo = ? WHERE user_id = ?",
        (new_online_elo, new_online_event_elo, user_id),
    )

    conn.commit()
    conn.close()

    return (new_online_elo, online_change, new_online_event_elo, online_event_change, True)


def update_elo_db_lifetime_only(user_id, user_display_name, did_win, opponent_id):
    """
    Update only the lifetime (online_elo) for a player, leaving event ELO unchanged.

    Used for top cut matches where only lifetime ELO should be affected.

    Returns:
        Tuple of (new_online_elo, online_change)
    """
    migrate_to_dual_elo_system()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    # Get player's current online lifetime ELO (or insert if new)
    cur.execute(
        "SELECT online_elo FROM overall_standings WHERE user_id=?", (user_id,)
    )
    player_row = cur.fetchone()

    if player_row:
        player_online_elo = player_row[0] if player_row[0] else 1500
    else:
        player_online_elo = 1500
        cur.execute(
            """INSERT OR IGNORE INTO overall_standings
               (user_id, user_display_name, online_elo, online_event_elo) VALUES (?, ?, ?, 1500)""",
            (user_id, user_display_name, player_online_elo),
        )

    # Get opponent's online lifetime ELO
    cur.execute(
        "SELECT online_elo FROM overall_standings WHERE user_id=?", (opponent_id,)
    )
    opponent_row = cur.fetchone()
    opponent_online_elo = (opponent_row[0] if opponent_row[0] else 1500) if opponent_row else 1500

    # Calculate new online lifetime ELO (K=32)
    new_online_elo = update_elo(player_online_elo, opponent_online_elo, did_win, k=32)
    online_change = new_online_elo - player_online_elo

    logger.info(
        "Player %s top-cut lifetime ELO updated: %d -> %d (%+d)",
        user_id, player_online_elo, new_online_elo, online_change,
    )

    # Update only online_elo; leave event ELOs untouched
    cur.execute(
        "UPDATE overall_standings SET online_elo = ? WHERE user_id = ?",
        (new_online_elo, user_id),
    )

    conn.commit()
    conn.close()

    return (new_online_elo, online_change)


def update_elo_db_ladder(
    user_id, user_display_name, did_win, opponent_id, elo_multiplier=1.0
):
    """
    Update the ELO database with ladder challenge match results (Discord bot / online games).

    Same as update_elo_db but applies an ELO multiplier to the change.
    For ladder challenges:
      - Non-Top16 player wins: 2x ELO gain
      - Top16 player loses: 0.5x ELO loss
      - If ELO difference < 100: normal (1x)

    Returns:
        Tuple of (new_online_elo, online_change, new_online_event_elo, online_event_change, event_active)
    """
    migrate_to_dual_elo_system()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    # Check for active event
    active_event = get_active_event()

    # Get player's current online ELOs (or insert if new)
    cur.execute(
        "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id=?", (user_id,)
    )
    player_row = cur.fetchone()

    if player_row:
        player_online_elo = player_row[0] if player_row[0] else 1500
        player_online_event_elo = player_row[1] if player_row[1] else 1500
    else:
        player_online_elo = 1500
        player_online_event_elo = 1500
        cur.execute(
            """INSERT OR IGNORE INTO overall_standings
               (user_id, user_display_name, online_elo, online_event_elo) VALUES (?, ?, ?, ?)""",
            (user_id, user_display_name, player_online_elo, player_online_event_elo),
        )

    # Get opponent's online ELOs
    cur.execute(
        "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id=?", (opponent_id,)
    )
    opponent_row = cur.fetchone()

    if opponent_row:
        opponent_online_elo = opponent_row[0] if opponent_row[0] else 1500
        opponent_online_event_elo = opponent_row[1] if opponent_row[1] else 1500
    else:
        opponent_online_elo = 1500
        opponent_online_event_elo = 1500

    # If no active event, don't update ELO
    if not active_event:
        conn.close()
        return (player_online_elo, 0, player_online_event_elo, 0, False)

    # Calculate base online ELO changes
    new_online_elo_base = update_elo(
        player_online_elo, opponent_online_elo, did_win, k=32
    )
    base_online_change = new_online_elo_base - player_online_elo

    event_k = calculate_event_k_value(active_event["start_date"])
    new_online_event_elo_base = update_elo(
        player_online_event_elo, opponent_online_event_elo, did_win, k=event_k
    )
    base_online_event_change = new_online_event_elo_base - player_online_event_elo

    # Apply multiplier
    online_change = round(base_online_change * elo_multiplier)
    online_event_change = round(base_online_event_change * elo_multiplier)

    new_online_elo = player_online_elo + online_change
    new_online_event_elo = player_online_event_elo + online_event_change

    logger.info(
        "Ladder online ELO update for %s: multiplier=%.1f, "
        "lifetime %d -> %d (%+d), event %d -> %d (%+d)",
        user_id, elo_multiplier,
        player_online_elo, new_online_elo, online_change,
        player_online_event_elo, new_online_event_elo, online_event_change,
    )

    cur.execute(
        "UPDATE overall_standings SET online_elo = ?, online_event_elo = ? WHERE user_id = ?",
        (new_online_elo, new_online_event_elo, user_id),
    )

    conn.commit()
    conn.close()

    return (new_online_elo, online_change, new_online_event_elo, online_event_change, True)


def _load_json_object(raw_value):
    """Safely parse a JSON object field from the audit log."""
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _table_exists(cursor, table_name):
    """Return True when a table exists in the current SQLite database."""
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _calculate_event_k_value_for_time(start_date, current_time):
    """Calculate the event K-value at a specific point in time."""
    days_elapsed = (current_time - start_date).days
    k_value = 16 + (days_elapsed * 2)
    return min(k_value, 32)


def _apply_standard_match_flow(winner_before, loser_before, k_value):
    """Apply the standard sequential winner-then-loser Elo update flow."""
    winner_after = update_elo(winner_before, loser_before, True, k=k_value)
    loser_after = update_elo(loser_before, winner_after, False, k=k_value)
    return {
        "winner_before": winner_before,
        "winner_after": winner_after,
        "loser_before": loser_before,
        "loser_after": loser_after,
        "winner_change": winner_after - winner_before,
        "loser_change": loser_after - loser_before,
    }


def _apply_special_ladder_flow(winner_before, loser_before, k_value):
    """Apply the special ladder stakes flow (2x winner, 0.5x challenger loss)."""
    base_result = _apply_standard_match_flow(winner_before, loser_before, k_value)
    winner_after = base_result["winner_after"] + round(base_result["winner_change"] * (2.0 - 1.0))
    loser_base_after = update_elo(loser_before, winner_after, False, k=k_value)
    loser_change = round((loser_base_after - loser_before) * 0.5)
    loser_after = loser_before + loser_change
    return {
        "winner_before": winner_before,
        "winner_after": winner_after,
        "loser_before": loser_before,
        "loser_after": loser_after,
        "winner_change": winner_after - winner_before,
        "loser_change": loser_change,
        "winner_base_change": base_result["winner_change"],
    }


def _resolve_match_from_exact_winner(
    winner_after,
    loser_after,
    exact_winner_change,
    k_value,
    special_ladder=False,
):
    """Resolve a match when the winner's exact total change is known."""
    winner_before = winner_after - exact_winner_change
    if winner_before < 1:
        raise ValueError("Invalid historical winner rating while reconstructing lifetime Elo.")

    candidates = []
    loser_min = max(1, loser_after)
    loser_max = loser_after + 64
    for loser_before in range(loser_min, loser_max + 1):
        if special_ladder:
            result = _apply_special_ladder_flow(winner_before, loser_before, k_value)
        else:
            result = _apply_standard_match_flow(winner_before, loser_before, k_value)

        if (
            result["winner_after"] == winner_after
            and result["loser_after"] == loser_after
            and result["winner_change"] == exact_winner_change
        ):
            candidates.append(result)

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError("Could not reconstruct historical lifetime Elo for this match.")
    raise ValueError("Lifetime Elo reconstruction is ambiguous for this match.")


def _resolve_match_from_exact_loser(
    winner_after,
    loser_after,
    exact_loser_change,
    k_value,
    special_ladder=False,
):
    """Resolve a match when the loser's exact total change is known."""
    loser_before = loser_after - exact_loser_change
    if loser_before < 1:
        raise ValueError("Invalid historical loser rating while reconstructing lifetime Elo.")

    candidates = []
    winner_min = max(1, winner_after - (64 if special_ladder else 32))
    winner_max = winner_after
    for winner_before in range(winner_min, winner_max + 1):
        if special_ladder:
            result = _apply_special_ladder_flow(winner_before, loser_before, k_value)
        else:
            result = _apply_standard_match_flow(winner_before, loser_before, k_value)

        if (
            result["winner_after"] == winner_after
            and result["loser_after"] == loser_after
            and result["loser_change"] == exact_loser_change
        ):
            candidates.append(result)

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError("Could not reconstruct historical lifetime Elo for this match.")
    raise ValueError("Lifetime Elo reconstruction is ambiguous for this match.")


def _resolve_lifetime_match_result(row, winner_after, loser_after, ladder_special=False):
    """Resolve one match's lifetime before/after ratings when exact deltas are available."""
    if row.get("is_top_cut"):
        raise ValueError(
            "Lifetime Elo cannot be reconstructed exactly for top cut matches because historical lifetime deltas were not stored."
        )

    if row.get("match_type") in NON_ELO_MATCH_TYPES:
        return {
            "winner_before": winner_after,
            "winner_after": winner_after,
            "loser_before": loser_after,
            "loser_after": loser_after,
        }

    k_value = 32
    exact_winner_change = row.get("winner_lifetime_elo_change")
    exact_loser_change = row.get("loser_lifetime_elo_change")

    if ladder_special and exact_winner_change is not None and row.get("did_win"):
        exact_winner_change = exact_winner_change + round(exact_winner_change)

    if row.get("did_win"):
        if exact_winner_change is None:
            raise ValueError("Missing winner lifetime delta for this match.")
        return _resolve_match_from_exact_winner(
            winner_after,
            loser_after,
            exact_winner_change,
            k_value,
            special_ladder=ladder_special,
        )

    if exact_loser_change is None:
        raise ValueError("Missing loser lifetime delta for this match.")
    return _resolve_match_from_exact_loser(
        winner_after,
        loser_after,
        exact_loser_change,
        k_value,
        special_ladder=ladder_special,
    )


def get_current_event_match_elo_snapshot(match_id: int):
    """Return before/after lifetime and event ELO for a current-event match."""
    active_event = get_active_event()
    if not active_event:
        raise ValueError("No active event is running right now.")

    event_start = active_event["start_date"]
    event_start_str = event_start.isoformat()

    match_conn = sqlite3.connect("match_records.db")
    match_conn.row_factory = sqlite3.Row
    match_cur = match_conn.cursor()

    match_cur.execute(
        """
        SELECT rowid as match_id, winner_id, winner_display_name, losser_id, losser_display_name,
               timestamp, match_type, did_win,
               winner_elo_change, loser_elo_change,
               winner_lifetime_elo_change, loser_lifetime_elo_change, event_k
        FROM match_records
        WHERE timestamp >= ?
        ORDER BY timestamp ASC, rowid ASC
        """,
        (event_start_str,),
    )
    match_rows = [dict(row) for row in match_cur.fetchall()]
    target_match = next((row for row in match_rows if row["match_id"] == match_id), None)
    if not target_match:
        match_conn.close()
        raise ValueError(
            f"Match #{match_id} was not found in the current active event."
        )

    participant_ids = set()
    for row in match_rows:
        participant_ids.add(row["winner_id"])
        participant_ids.add(row["losser_id"])

    ladder_challengers = {}
    if _table_exists(match_cur, "ladder_challenges"):
        match_cur.execute(
            """
            SELECT challenge_id, challenger_id, match_id
            FROM ladder_challenges
            WHERE match_id IS NOT NULL
            """
        )
        ladder_challengers = {
            row[2]: {"challenge_id": row[0], "challenger_id": row[1]}
            for row in match_cur.fetchall()
            if row[2] is not None
        }

    spot_reset_events = []
    top_cut_match_ids = set()
    if _table_exists(match_cur, "admin_audit_log"):
        match_cur.execute(
            """
            SELECT id, timestamp, target_id, previous_state, new_state
            FROM admin_audit_log
            WHERE action = 'spot_elo_reset' AND timestamp >= ?
            ORDER BY timestamp ASC, id ASC
            """,
            (event_start_str,),
        )
        for audit_row in match_cur.fetchall():
            previous_state = _load_json_object(audit_row[3])
            new_state = _load_json_object(audit_row[4])
            if "event_elo" not in new_state:
                continue
            if new_state.get("avatar"):
                continue  # an avatar entry's reset; the per-player replay never saw it

            try:
                target_user_id = int(audit_row[2]) if audit_row[2] is not None else None
            except (TypeError, ValueError):
                target_user_id = None

            if target_user_id is None:
                continue

            participant_ids.add(target_user_id)
            spot_reset_events.append(
                {
                    "id": audit_row[0],
                    "timestamp": datetime.datetime.fromisoformat(audit_row[1]),
                    "target_id": target_user_id,
                    "previous_event_elo": previous_state.get("event_elo", 1500),
                    "new_event_elo": new_state["event_elo"],
                }
            )

        match_cur.execute(
            """
            SELECT new_state
            FROM admin_audit_log
            WHERE action = 'top_cut_report' AND timestamp >= ?
            ORDER BY id ASC
            """,
            (event_start_str,),
        )
        for (new_state_raw,) in match_cur.fetchall():
            new_state = _load_json_object(new_state_raw)
            logged_match_id = new_state.get("match_id")
            if logged_match_id is not None:
                top_cut_match_ids.add(logged_match_id)

    match_conn.close()

    elo_conn = sqlite3.connect("elo.db")
    elo_conn.row_factory = sqlite3.Row
    elo_cur = elo_conn.cursor()

    current_lifetime_state = {user_id: 1500 for user_id in participant_ids}
    current_event_state = {user_id: 1500 for user_id in participant_ids}
    if participant_ids:
        placeholders = ", ".join("?" for _ in participant_ids)
        elo_cur.execute(
            f"""
            SELECT user_id,
                   COALESCE(online_elo, 1500) AS current_lifetime_elo,
                   COALESCE(online_event_elo, 1500) AS current_event_elo
            FROM overall_standings
            WHERE user_id IN ({placeholders})
            """,
            tuple(participant_ids),
        )
        for row in elo_cur.fetchall():
            current_lifetime_state[row["user_id"]] = row["current_lifetime_elo"]
            current_event_state[row["user_id"]] = row["current_event_elo"]

    elo_conn.close()

    operations = []
    for row in match_rows:
        operations.append(
            {
                "kind": "match",
                "timestamp": datetime.datetime.fromisoformat(row["timestamp"]),
                "sort_id": row["match_id"],
                "match": row,
            }
        )
    for reset in spot_reset_events:
        operations.append(
            {
                "kind": "spot_reset",
                "timestamp": reset["timestamp"],
                "sort_id": reset["id"],
                "reset": reset,
            }
        )

    operations.sort(
        key=lambda op: (
            op["timestamp"],
            0 if op["kind"] == "spot_reset" else 1,
            op["sort_id"],
        )
    )

    event_state = {user_id: 1500 for user_id in participant_ids}
    season_games = {}  # rated games so far, per player: sets each player's K
    event_snapshots = {}

    for operation in operations:
        if operation["kind"] == "spot_reset":
            reset = operation["reset"]
            event_state[reset["target_id"]] = reset["new_event_elo"]
            continue

        row = operation["match"]
        match_id_value = row["match_id"]
        winner_id = row["winner_id"]
        loser_id = row["losser_id"]
        match_timestamp = operation["timestamp"]
        # The K the match was recorded at; rows from before K was stored are replayed
        event_k = row.get("event_k") or match_event_k(
            season_games.get(winner_id, 0), season_games.get(loser_id, 0)
        )
        challenger_info = ladder_challengers.get(match_id_value)
        challenger_id = challenger_info["challenger_id"] if challenger_info else None
        winner_before_event = event_state.get(winner_id, 1500)
        loser_before_event = event_state.get(loser_id, 1500)

        is_top_cut = match_id_value in top_cut_match_ids
        is_testing = row.get("match_type") in NON_ELO_MATCH_TYPES
        is_casual = is_testing and not is_top_cut
        ladder_special = False

        if is_casual:
            event_result = {
                "winner_before": winner_before_event,
                "winner_after": winner_before_event,
                "loser_before": loser_before_event,
                "loser_after": loser_before_event,
            }
        elif is_top_cut:
            event_result = {
                "winner_before": winner_before_event,
                "winner_after": winner_before_event,
                "loser_before": loser_before_event,
                "loser_after": loser_before_event,
            }
        else:
            if challenger_id and challenger_id != winner_id:
                if abs(winner_before_event - loser_before_event) >= 100:
                    ladder_special = True

            if ladder_special:
                event_result = _apply_special_ladder_flow(
                    winner_before_event,
                    loser_before_event,
                    event_k,
                )
            else:
                event_result = _apply_standard_match_flow(
                    winner_before_event,
                    loser_before_event,
                    event_k,
                )

        event_state[winner_id] = event_result["winner_after"]
        event_state[loser_id] = event_result["loser_after"]
        if not (is_casual or is_top_cut):
            season_games[winner_id] = season_games.get(winner_id, 0) + 1
            season_games[loser_id] = season_games.get(loser_id, 0) + 1

        event_snapshots[match_id_value] = {
            "winner_before": event_result["winner_before"],
            "winner_after": event_result["winner_after"],
            "loser_before": event_result["loser_before"],
            "loser_after": event_result["loser_after"],
            "is_top_cut": is_top_cut,
            "is_casual": is_casual,
            "is_ladder_match": challenger_id is not None,
            "ladder_special": ladder_special,
            "event_k": event_k,
            "timestamp": match_timestamp,
        }

    lifetime_state = dict(current_lifetime_state)
    lifetime_snapshot = None
    lifetime_unavailable_reason = None

    for row in reversed(match_rows):
        match_id_value = row["match_id"]
        winner_id = row["winner_id"]
        loser_id = row["losser_id"]
        event_snapshot = event_snapshots[match_id_value]
        row["is_top_cut"] = event_snapshot["is_top_cut"]

        winner_after_lifetime = lifetime_state.get(winner_id, 1500)
        loser_after_lifetime = lifetime_state.get(loser_id, 1500)

        try:
            resolved_lifetime = _resolve_lifetime_match_result(
                row,
                winner_after_lifetime,
                loser_after_lifetime,
                ladder_special=event_snapshot["ladder_special"],
            )
        except ValueError as exc:
            lifetime_unavailable_reason = str(exc)
            if match_id_value == match_id:
                break
            lifetime_snapshot = None
            break

        lifetime_state[winner_id] = resolved_lifetime["winner_before"]
        lifetime_state[loser_id] = resolved_lifetime["loser_before"]

        if match_id_value == match_id:
            lifetime_snapshot = resolved_lifetime
            break

    snapshot = event_snapshots.get(match_id)
    if not snapshot:
        raise ValueError(
            f"Could not reconstruct Elo history for match #{match_id}."
        )

    target_timestamp = snapshot["timestamp"]
    prior_player_resets = [
        reset
        for reset in spot_reset_events
        if reset["timestamp"] <= target_timestamp
        and reset["target_id"] in (target_match["winner_id"], target_match["losser_id"])
    ]

    notes = []
    if prior_player_resets:
        notes.append(
            f"Accounts for {len(prior_player_resets)} prior manual event Elo reset(s) affecting these players."
        )
    if snapshot["is_casual"]:
        notes.append("Casual/testing match: no Elo changed.")
    elif snapshot["is_top_cut"]:
        notes.append("Top cut match: event Elo stayed unchanged.")
    elif snapshot["ladder_special"]:
        notes.append("Ladder challenge with special stakes: winner gained 2x and challenger lost 0.5x.")
    elif snapshot["is_ladder_match"]:
        notes.append("Ladder challenge match with normal stakes.")
    if lifetime_snapshot is None and lifetime_unavailable_reason:
        notes.append(f"Lifetime Elo unavailable: {lifetime_unavailable_reason}")

    # Avatar-mode events: the ladder that counts is the avatars' — report the
    # stored per-avatar before/after instead of the per-player replay.
    winner_event = {"event_before": snapshot["winner_before"], "event_after": snapshot["winner_after"]}
    loser_event = {"event_before": snapshot["loser_before"], "event_after": snapshot["loser_after"]}
    avatar_row = None
    if active_event.get("elo_mode") == AVATAR_MODE:
        conn = sqlite3.connect("match_records.db")
        conn.row_factory = sqlite3.Row
        try:
            avatar_row = conn.execute(
                "SELECT winner_avatar, loser_avatar, winner_avatar_elo_change, loser_avatar_elo_change, "
                "winner_avatar_elo_after, loser_avatar_elo_after FROM match_records WHERE rowid = ?",
                (match_id,),
            ).fetchone()
        finally:
            conn.close()
    if avatar_row and avatar_row["winner_avatar_elo_after"] is not None:
        winner_event = {
            "avatar": avatar_row["winner_avatar"],
            "event_before": avatar_row["winner_avatar_elo_after"] - (avatar_row["winner_avatar_elo_change"] or 0),
            "event_after": avatar_row["winner_avatar_elo_after"],
        }
        loser_event = {
            "avatar": avatar_row["loser_avatar"],
            "event_before": avatar_row["loser_avatar_elo_after"] - (avatar_row["loser_avatar_elo_change"] or 0),
            "event_after": avatar_row["loser_avatar_elo_after"],
        }
        notes.append("Avatar-mode event: event Elo shown is each player's entry for the avatar they played.")

    return {
        "event_name": active_event["event_name"],
        "event_start": event_start,
        "event_k": snapshot["event_k"],
        "match_id": match_id,
        "match_timestamp": target_timestamp,
        "match_type": target_match.get("match_type") or "ranked",
        "winner_id": target_match["winner_id"],
        "winner_display_name": target_match["winner_display_name"],
        "loser_id": target_match["losser_id"],
        "loser_display_name": target_match["losser_display_name"],
        "winner": {
            "lifetime_before": lifetime_snapshot["winner_before"] if lifetime_snapshot else None,
            "lifetime_after": lifetime_snapshot["winner_after"] if lifetime_snapshot else None,
            **winner_event,
        },
        "loser": {
            "lifetime_before": lifetime_snapshot["loser_before"] if lifetime_snapshot else None,
            "lifetime_after": lifetime_snapshot["loser_after"] if lifetime_snapshot else None,
            **loser_event,
        },
        "notes": notes,
    }


# --- Match Reporting ---


def _calculate_both_elo_changes(
    winner_elo,
    winner_event_elo,
    loser_elo,
    loser_event_elo,
    event_k,
    elo_multiplier_winner=1.0,
    elo_multiplier_loser=1.0,
):
    """Calculate ELO changes for both players atomically.

    Uses the sequential calculation method:
      1. Winner change is computed vs loser's *current* ELO.
      2. Loser change is computed vs winner's *new* ELO (after step 1).

    This matches the old two-call flow while keeping everything in one place
    so the stored changes are always accurate.

    Returns:
        (winner_lifetime_change, winner_event_change,
         loser_lifetime_change, loser_event_change)
    """
    # Winner base changes (opponent = loser's current ELO)
    winner_base_lifetime = update_elo(winner_elo, loser_elo, True, k=32) - winner_elo
    winner_base_event = update_elo(winner_event_elo, loser_event_elo, True, k=event_k) - winner_event_elo

    # Apply multiplier to winner
    winner_lifetime_change = round(winner_base_lifetime * elo_multiplier_winner)
    winner_event_change = round(winner_base_event * elo_multiplier_winner)

    # Winner's new ELOs (used as opponent for loser calculation)
    winner_new_elo = winner_elo + winner_lifetime_change
    winner_new_event_elo = winner_event_elo + winner_event_change

    # Loser base changes (opponent = winner's NEW ELO — sequential)
    loser_base_lifetime = update_elo(loser_elo, winner_new_elo, False, k=32) - loser_elo
    loser_base_event = update_elo(loser_event_elo, winner_new_event_elo, False, k=event_k) - loser_event_elo

    # Apply multiplier to loser
    loser_lifetime_change = round(loser_base_lifetime * elo_multiplier_loser)
    loser_event_change = round(loser_base_event * elo_multiplier_loser)

    return (winner_lifetime_change, winner_event_change, loser_lifetime_change, loser_event_change)


def _calculate_event_changes(
    winner_event_elo, loser_event_elo, event_k, elo_multiplier_winner=1.0, elo_multiplier_loser=1.0,
):
    """One ladder's (winner_change, loser_change), sequential like the lifetime ladder."""
    winner_change = round(
        (update_elo(winner_event_elo, loser_event_elo, True, k=event_k) - winner_event_elo)
        * elo_multiplier_winner
    )
    loser_change = round(
        (update_elo(loser_event_elo, winner_event_elo + winner_change, False, k=event_k) - loser_event_elo)
        * elo_multiplier_loser
    )
    return winner_change, loser_change


async def resolve_match_avatars(pairing_id, winner_id, loser_id, winner_avatar, loser_avatar,
                                winner_deck_url=None, loser_deck_url=None):
    """Both avatars for an Avatar-mode match.

    Explicit avatars (admin reports) win; then the avatars locked to the
    pairing when the match was made; then, as a last resort for reports
    without a pairing, a read of each deck link.
    """
    locked = get_pairing_avatars(pairing_id)
    winner_avatar = winner_avatar or locked.get(winner_id)
    loser_avatar = loser_avatar or locked.get(loser_id)
    if not winner_avatar and winner_deck_url:
        winner_avatar = await read_deck_avatar(winner_deck_url)
    if not loser_avatar and loser_deck_url:
        loser_avatar = await read_deck_avatar(loser_deck_url)
    return winner_avatar, loser_avatar


_VALID_DECK_URL_PREFIXES = (
    "https://curiosa.io/decks/",
    "https://sorcerytcg.com/decks/",
)


def _is_valid_deck_url(url: str) -> bool:
    """Return True if url is a proper deck URL with a non-empty deck ID.

    Accepts sorcerytcg.com / curiosa.io decks and Play Sorcery Online deck
    links (https://playsorceryonline.com/?deck=<id>).
    """
    if not url or not isinstance(url, str):
        return False
    if get_pso_deck_id(url):
        return True
    base = url.split("?")[0].rstrip("/")
    for prefix in _VALID_DECK_URL_PREFIXES:
        if base.startswith(prefix):
            deck_id = base[len(prefix):]
            return bool(deck_id)
    return False


async def _update_deck_data(match_id: int, winner_url: str, loser_url: str, table: str = "match_records") -> None:
    """Background task: fetch deck JSON from Curiosa and update the match record.

    Runs after record_match() completes so that deck scraping never blocks the
    Discord event loop.  If Curiosa is unavailable the match record stays with
    empty '{}' deck data — same as today's failure behaviour.
    """
    winner_json = "{}"
    loser_json = "{}"
    if _is_valid_deck_url(winner_url):
        winner_json = await scrape_curosa_async(winner_url)
        if winner_json == "{}":
            logger.warning("_update_deck_data: failed to fetch winner deck json for match %s url=%s", match_id, winner_url)
        else:
            logger.info("_update_deck_data: fetched winner deck json for match %s", match_id)
    if _is_valid_deck_url(loser_url):
        loser_json = await scrape_curosa_async(loser_url)
        if loser_json == "{}":
            logger.warning("_update_deck_data: failed to fetch loser deck json for match %s url=%s", match_id, loser_url)
        else:
            logger.info("_update_deck_data: fetched loser deck json for match %s", match_id)

    try:
        conn = sqlite3.connect("match_records.db")
        if table == "rumble_match_records":
            conn.execute(
                "UPDATE rumble_match_records SET json_deck_data_winner = ?, json_deck_data_loser = ? WHERE rowid = ?",
                (winner_json, loser_json, match_id),
            )
        else:
            conn.execute(
                "UPDATE match_records SET json_deck_data = ?, json_deck_data_winner = ?, json_deck_data_loser = ? WHERE rowid = ?",
                (winner_json, winner_json, loser_json, match_id),
            )
        conn.commit()
        conn.close()
        logger.info("_update_deck_data: updated deck data for match_id=%s in %s", match_id, table)
    except Exception as exc:
        logger.warning("_update_deck_data: failed to write deck data for match %s: %s", match_id, exc)


# Tables whose deck JSON the startup backfill repairs. Ended events move their
# matches into the archive, and the profile page reads both, so a deck that was
# never fetched (e.g. a PSO link from before the bot accepted them) has to be
# recovered there too.
_BACKFILL_TABLES = ("match_records", "match_records_archive")


async def backfill_deck_data() -> None:
    """Background startup task: fetch deck JSON for any records with valid URLs but empty JSON.

    Runs once on bot startup to recover data for matches that were recorded when
    the deck fetch could not handle the link (e.g. wrong WHERE clause, SSL
    failures, or a Play Sorcery Online link from before those were supported).
    Covers the live table and the event archive.
    Rate-limited to ~1 request per second to avoid hammering Curiosa.
    """
    import asyncio as _asyncio

    to_backfill = []  # (table, rowid, winner_url, loser_url, winner_json, loser_json)
    for table in _BACKFILL_TABLES:
        try:
            conn = sqlite3.connect("match_records.db")
            cur = conn.cursor()
            # Fetch records where either deck JSON column is missing — filter valid URLs in Python
            cur.execute(
                f"""
                SELECT rowid, curiosa_url_winner, curiosa_url_loser,
                       json_deck_data_winner, json_deck_data_loser
                FROM {table}
                WHERE (json_deck_data_winner IS NULL OR json_deck_data_winner = '{{}}')
                   OR (json_deck_data_loser IS NULL OR json_deck_data_loser = '{{}}')
                """
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as exc:
            logger.warning("backfill_deck_data: failed to query %s: %s", table, exc)
            continue

        # Filter to only rows that have at least one valid URL with missing JSON
        to_backfill.extend(
            (table, *row) for row in rows
            if (_is_valid_deck_url(row[1]) and (not row[3] or row[3] == "{}"))
            or (_is_valid_deck_url(row[2]) and (not row[4] or row[4] == "{}"))
        )

    if not to_backfill:
        logger.info("backfill_deck_data: nothing to backfill")
        return

    logger.info("backfill_deck_data: backfilling %d records", len(to_backfill))
    updated = 0
    for table, rowid, winner_url, loser_url, existing_winner_json, existing_loser_json in to_backfill:
        winner_json = existing_winner_json or "{}"
        loser_json = existing_loser_json or "{}"

        if _is_valid_deck_url(winner_url) and (not existing_winner_json or existing_winner_json == "{}"):
            winner_json = await scrape_curosa_async(winner_url)

        if _is_valid_deck_url(loser_url) and (not existing_loser_json or existing_loser_json == "{}"):
            loser_json = await scrape_curosa_async(loser_url)

        if winner_json != "{}" or loser_json != "{}":
            try:
                conn = sqlite3.connect("match_records.db")
                conn.execute(
                    f"UPDATE {table} SET json_deck_data = ?, json_deck_data_winner = ?, json_deck_data_loser = ? WHERE rowid = ?",
                    (winner_json, winner_json, loser_json, rowid),
                )
                conn.commit()
                conn.close()
                updated += 1
            except Exception as exc:
                logger.warning("backfill_deck_data: failed to update %s rowid=%s: %s", table, rowid, exc)

        await _asyncio.sleep(1)  # rate-limit: 1 req/sec

    logger.info("backfill_deck_data: updated %d records", updated)


async def record_match(
    reporter_id,
    winner_id,
    winner_global,
    loser_id,
    loser_global,
    first_player,
    match_time,
    match_comment,
    winner_deck_url,
    loser_deck_url,
    winner_went_first,
    loser_went_first,
    match_type="ranked",
    elo_multiplier_winner=1.0,
    elo_multiplier_loser=1.0,
    pairing_id=None,
    winner_avatar=None,
    loser_avatar=None,
):
    """Record a completed match: calculate ELOs atomically, update DB, insert match record.

    In an Avatar-mode event the two avatars' entries move too (see
    resolve_match_avatars for where the avatars come from). The per-player
    event ELO keeps updating either way, so the recording path is the same
    in both modes; the mode only decides which ladder is shown and used.

    Operation order (safe across two SQLite files):
      1. Calculate both players' ELO changes — pure math, no DB writes yet.
      2. Apply multipliers (ladder stakes) — already in the calculation.
      3. Write both ELOs in a single elo.db transaction.
      4. Insert match record in match_records.db with correct ELO values and empty deck JSON.
      5. Fire asyncio.create_task(_update_deck_data(...)) — fills deck JSON in the background.

    If step 4 fails after step 3, ELOs are updated but no match record exists —
    recoverable by an admin.  Previously a crash could leave only one player's
    ELO updated, which is much harder to detect.
    If Curiosa is down, step 5 completes silently and deck JSON stays '{}'.

    Returns:
        (match_id, winner_elo_change, loser_elo_change,
         winner_lifetime_change, loser_lifetime_change, event_active)

        winner_elo_change / loser_elo_change: event ELO delta (0 if no active event
        or match_type in NON_ELO_MATCH_TYPES).
    """
    logger.info(
        "record_match: winner=%s (id=%s) loser=%s (id=%s) type=%s",
        winner_global, winner_id, loser_global, loser_id, match_type,
    )

    event_k = None  # the season K-factor this match was played at (rated season games only)

    # Per-avatar ladder (Avatar-mode events only; stays None otherwise)
    avatar_event_id = None
    winner_avatar_change = loser_avatar_change = None
    winner_avatar_after = loser_avatar_after = None

    # ── Step 1: calculate ELO changes ──
    if match_type in NON_ELO_MATCH_TYPES:
        winner_elo_change = 0
        loser_elo_change = 0
        winner_lifetime_change = 0
        loser_lifetime_change = 0
        event_active = False
        # These won't be written but need names for the INSERT below
        winner_new_elo = winner_new_event_elo = None
        loser_new_elo = loser_new_event_elo = None
    else:
        migrate_to_dual_elo_system()
        active_event = get_active_event()
        event_active = active_event is not None

        conn_elo = sqlite3.connect("elo.db")
        cur_elo = conn_elo.cursor()
        cur_elo.execute(
            "SELECT online_elo, online_event_elo, online_event_games FROM overall_standings WHERE user_id=?",
            (winner_id,),
        )
        row = cur_elo.fetchone()
        winner_elo = (row[0] or 1500) if row else 1500
        winner_event_elo = (row[1] or 1500) if row else 1500
        winner_event_games = (row[2] or 0) if row else 0

        cur_elo.execute(
            "SELECT online_elo, online_event_elo, online_event_games FROM overall_standings WHERE user_id=?",
            (loser_id,),
        )
        row = cur_elo.fetchone()
        loser_elo = (row[0] or 1500) if row else 1500
        loser_event_elo = (row[1] or 1500) if row else 1500
        loser_event_games = (row[2] or 0) if row else 0
        conn_elo.close()

        if not event_active:
            winner_elo_change = 0
            loser_elo_change = 0
            winner_lifetime_change = 0
            loser_lifetime_change = 0
            winner_new_elo = winner_new_event_elo = None
            loser_new_elo = loser_new_event_elo = None
        else:
            # Each player's season K ramps up with their own games; the match
            # is played at the lower of the two
            event_k = match_event_k(winner_event_games, loser_event_games)
            winner_lifetime_change, winner_elo_change, loser_lifetime_change, loser_elo_change = (
                _calculate_both_elo_changes(
                    winner_elo, winner_event_elo,
                    loser_elo, loser_event_elo,
                    event_k,
                    elo_multiplier_winner,
                    elo_multiplier_loser,
                )
            )
            winner_new_elo = winner_elo + winner_lifetime_change
            winner_new_event_elo = winner_event_elo + winner_elo_change
            loser_new_elo = loser_elo + loser_lifetime_change
            loser_new_event_elo = loser_event_elo + loser_elo_change

            if active_event.get("elo_mode") == AVATAR_MODE:
                winner_avatar, loser_avatar = await resolve_match_avatars(
                    pairing_id, winner_id, loser_id, winner_avatar, loser_avatar,
                    winner_deck_url, loser_deck_url,
                )
                if winner_avatar and loser_avatar:
                    avatar_event_id = active_event["event_id"]
                    winner_avatar_elo = get_avatar_event_elo(avatar_event_id, winner_id, winner_avatar)
                    loser_avatar_elo = get_avatar_event_elo(avatar_event_id, loser_id, loser_avatar)
                    winner_avatar_change, loser_avatar_change = _calculate_event_changes(
                        winner_avatar_elo, loser_avatar_elo, event_k,
                        elo_multiplier_winner, elo_multiplier_loser,
                    )
                    winner_avatar_after = winner_avatar_elo + winner_avatar_change
                    loser_avatar_after = loser_avatar_elo + loser_avatar_change
                else:
                    logger.warning(
                        "record_match: Avatar-mode match without both avatars "
                        "(winner=%s avatar=%s, loser=%s avatar=%s, pairing=%s) — avatar ladder not updated",
                        winner_id, winner_avatar, loser_id, loser_avatar, pairing_id,
                    )

    if avatar_event_id is None:
        # Player mode (or unknown avatars): avatars aren't part of the record
        winner_avatar = loser_avatar = None

    # ── Step 2: write both ELOs atomically ──
    if match_type not in NON_ELO_MATCH_TYPES and event_active:
        update_both_player_elos(
            winner_id, winner_global,
            winner_new_elo, winner_new_event_elo,
            loser_id, loser_global,
            loser_new_elo, loser_new_event_elo,
        )
        logger.info(
            "record_match ELO update: %s lifetime %d→%d (%+d) event %d→%d (%+d) | "
            "%s lifetime %d→%d (%+d) event %d→%d (%+d)",
            winner_global, winner_elo, winner_new_elo, winner_lifetime_change,
            winner_event_elo, winner_new_event_elo, winner_elo_change,
            loser_global, loser_elo, loser_new_elo, loser_lifetime_change,
            loser_event_elo, loser_new_event_elo, loser_elo_change,
        )
        if avatar_event_id is not None:
            record_avatar_results(avatar_event_id, [
                (winner_id, winner_global, winner_avatar, winner_avatar_after),
                (loser_id, loser_global, loser_avatar, loser_avatar_after),
            ])
            logger.info(
                "record_match avatar ELO: %s (%s) %+d → %d | %s (%s) %+d → %d",
                winner_global, winner_avatar, winner_avatar_change, winner_avatar_after,
                loser_global, loser_avatar, loser_avatar_change, loser_avatar_after,
            )

    # ── Step 3: insert match record (deck data filled in async below) ──
    create_db()
    now_iso = datetime.datetime.now().isoformat()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    if match_type == "rumble":
        # Rumble matches go into a separate table to keep them out of overall stats
        cur.execute(
            "INSERT INTO rumble_match_records (reporter_id, winner_id, winner_display_name, "
            "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
            "curiosa_url_winner, curiosa_url_loser, match_comment, "
            "json_deck_data_winner, json_deck_data_loser, "
            "winner_went_first, loser_went_first) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reporter_id,
                winner_id, winner_global,
                loser_id, loser_global,
                True,
                now_iso,
                first_player,
                match_time,
                winner_deck_url,
                loser_deck_url,
                match_comment,
                "{}",  # json_deck_data_winner
                "{}",  # json_deck_data_loser
                winner_went_first,
                loser_went_first,
            ),
        )
        table_name = "rumble_match_records"
    else:
        cur.execute(
            "INSERT INTO match_records (reporter_id, winner_id, winner_display_name, "
            "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
            "curiosa_url, curiosa_url_winner, curiosa_url_loser, match_comment, "
            "json_deck_data, json_deck_data_winner, json_deck_data_loser, "
            "winner_elo_change, loser_elo_change, "
            "winner_lifetime_elo_change, loser_lifetime_elo_change, "
            "winner_went_first, loser_went_first, match_type, "
            "winner_lifetime_elo_after, loser_lifetime_elo_after, pairing_id, voice, "
            "winner_avatar, loser_avatar, winner_avatar_elo_change, loser_avatar_elo_change, "
            "winner_avatar_elo_after, loser_avatar_elo_after, event_k) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?)",
            (
                reporter_id,
                winner_id, winner_global,
                loser_id, loser_global,
                True,
                now_iso,
                first_player,
                match_time,
                winner_deck_url,  # curiosa_url (backward compat)
                winner_deck_url,
                loser_deck_url,
                match_comment,
                "{}",  # json_deck_data — filled in by _update_deck_data background task
                "{}",  # json_deck_data_winner
                "{}",  # json_deck_data_loser
                winner_elo_change,
                loser_elo_change,
                winner_lifetime_change,
                loser_lifetime_change,
                winner_went_first,
                loser_went_first,
                match_type,
                winner_new_elo,
                loser_new_elo,
                pairing_id,
                1 if get_pairing_voice(pairing_id) else 0,
                winner_avatar,
                loser_avatar,
                winner_avatar_change,
                loser_avatar_change,
                winner_avatar_after,
                loser_avatar_after,
                event_k,
            ),
        )
        table_name = "match_records"

    match_id = cur.lastrowid
    conn.commit()
    conn.close()

    # ── Step 4: scrape deck data asynchronously (non-blocking) ──
    asyncio.create_task(_update_deck_data(match_id, winner_deck_url, loser_deck_url, table_name))

    return (match_id, winner_elo_change, loser_elo_change, winner_lifetime_change, loser_lifetime_change, event_active)


# --- Event Management ---


def start_new_event(event_name, elo_mode=PLAYER_MODE, scheduled_end_at=None):
    """
    Start a new event, archiving any active event first.

    Args:
        event_name: Name for the new event
        elo_mode: "player" (one event ELO per player) or "avatar" (one per
            player and avatar). Locked for the life of the event.
        scheduled_end_at: Unix seconds at which the season ends by itself
            (the bot then takes the top cut and drafts the postseason
            bracket), or None to end it by hand.

    Returns:
        dict with new event info and optional previous event summary
    """
    elo_mode = (elo_mode or PLAYER_MODE).strip().lower()
    if elo_mode not in ELO_MODES:
        raise ValueError(f"elo_mode must be one of {', '.join(ELO_MODES)}")

    create_events_table()
    create_match_records_archive()
    migrate_to_dual_elo_system()

    previous_event_summary = None

    # Check for and archive any active event
    active_event = get_active_event()
    if active_event:
        previous_event_summary = end_current_event()

    # Create new event
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    start_date = datetime.datetime.now().isoformat()
    cur.execute(
        "INSERT INTO events (event_name, start_date, is_active, elo_mode, scheduled_end_at) "
        "VALUES (?, ?, 1, ?, ?)",
        (event_name, start_date, elo_mode, scheduled_end_at),
    )
    event_id = cur.lastrowid

    # Reset all players' event ELOs to 1500 (both paper and online). Avatar
    # entries need no reset: they're keyed by event, so a new event starts empty.
    cur.execute(
        "UPDATE overall_standings SET paper_event_elo = 1500, online_event_elo = 1500, online_event_games = 0"
    )

    conn.commit()
    conn.close()

    return {
        "event_id": event_id,
        "event_name": event_name,
        "start_date": datetime.datetime.fromisoformat(start_date),
        "elo_mode": elo_mode,
        "scheduled_end_at": scheduled_end_at,
        "previous_event": previous_event_summary,
    }


def end_current_event():
    """
    End the current active event and archive its data.

    Returns:
        dict with event summary (top players, total matches) or None
    """
    # Make sure the archive tables carry every column the INSERTs below
    # expect. These migrations used to run only from start_new_event(), so
    # !end_event on a long-lived database could hit an archive table that
    # predated newer columns (e.g. match_records_archive.voice).
    create_events_table()
    create_match_records_archive()

    active_event = get_active_event()
    if not active_event:
        return None

    event_id = active_event["event_id"]
    event_name = active_event["event_name"]

    # Archive standings
    conn_elo = sqlite3.connect("elo.db")
    cur_elo = conn_elo.cursor()

    # Get event participants from match_records
    from repositories.elo_repo import get_event_participant_ids
    event_start_str = active_event["start_date"].isoformat()
    event_participants = get_event_participant_ids(event_start_str)

    # Get all players who participated in the event
    cur_elo.execute("""SELECT user_id, user_display_name, paper_event_elo, online_event_elo
                       FROM overall_standings""")
    all_players = [(uid, name, paper_elo, online_elo)
                   for uid, name, paper_elo, online_elo in cur_elo.fetchall()
                   if uid in event_participants]

    # Paper and online are separate ladders, so each keeps its own ranking
    paper_standings = [(uid, name, paper_elo) for uid, name, paper_elo, _ in all_players]
    online_standings = [(uid, name, online_elo) for uid, name, _, online_elo in all_players]

    # Sort by ELO descending
    paper_standings.sort(key=lambda x: x[2], reverse=True)
    online_standings.sort(key=lambda x: x[2], reverse=True)

    # The event's standings are the online ladder: participants come from
    # Discord match records, and overall_standings.paper_event_elo is only
    # ever reset to 1500 (paper ratings live in the web app's paper_standings).
    # This used to archive max(paper, online), which turned every player who
    # finished below 1500 online into a "1500" ranked by the all-tied paper
    # list, scattering 1500s through the past event leaderboard.
    standings = list(online_standings)

    # Create rank maps
    paper_ranks = {uid: rank for rank, (uid, _, _) in enumerate(paper_standings, start=1)}
    online_ranks = {uid: rank for rank, (uid, _, _) in enumerate(online_standings, start=1)}

    # Archive standings (one row per player with both paper and online data)
    archived_at = datetime.datetime.now().isoformat()
    for user_id, display_name, paper_elo, online_elo in all_players:
        cur_elo.execute(
            """INSERT INTO event_standings_archive
               (event_id, user_id, user_display_name, final_event_elo, final_rank,
                final_paper_event_elo, final_paper_rank, final_online_event_elo, final_online_rank, archived_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, user_id, display_name, online_elo, online_ranks[user_id],
             paper_elo, paper_ranks.get(user_id), online_elo, online_ranks.get(user_id), archived_at),
        )

    # Mark event as ended
    cur_elo.execute(
        "UPDATE events SET is_active = 0, end_date = ? WHERE event_id = ?",
        (archived_at, event_id),
    )

    conn_elo.commit()
    conn_elo.close()

    # Archive match records
    conn_match = sqlite3.connect("match_records.db")
    cur_match = conn_match.cursor()

    # Copy all matches to archive
    cur_match.execute("SELECT * FROM match_records")
    matches = cur_match.fetchall()
    match_count = len(matches)

    # Get column names from match_records
    cur_match.execute("PRAGMA table_info(match_records)")
    columns = [col[1] for col in cur_match.fetchall()]

    for match in matches:
        match_dict = dict(zip(columns, match))
        cur_match.execute(
            """INSERT INTO match_records_archive
               (event_id, original_match_id, reporter_id, winner_id, winner_display_name,
                losser_id, losser_display_name, did_win, timestamp, first_player, match_time,
                curiosa_url, curiosa_url_winner, curiosa_url_loser, match_comment,
                json_deck_data, json_deck_data_winner, json_deck_data_loser,
                winner_elo_change, loser_elo_change,
                winner_lifetime_elo_change, loser_lifetime_elo_change,
                winner_went_first, loser_went_first,
                winner_lifetime_elo_after, loser_lifetime_elo_after,
                match_type, voice, archived_at,
                winner_avatar, loser_avatar, winner_avatar_elo_change, loser_avatar_elo_change,
                winner_avatar_elo_after, loser_avatar_elo_after, event_k)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                match_dict.get("match_id"),
                match_dict.get("reporter_id"),
                match_dict.get("winner_id"),
                match_dict.get("winner_display_name"),
                match_dict.get("losser_id"),
                match_dict.get("losser_display_name"),
                match_dict.get("did_win"),
                match_dict.get("timestamp"),
                match_dict.get("first_player"),
                match_dict.get("match_time"),
                match_dict.get("curiosa_url"),
                match_dict.get("curiosa_url_winner"),
                match_dict.get("curiosa_url_loser"),
                match_dict.get("match_comment"),
                match_dict.get("json_deck_data"),
                match_dict.get("json_deck_data_winner"),
                match_dict.get("json_deck_data_loser"),
                match_dict.get("winner_elo_change"),
                match_dict.get("loser_elo_change"),
                match_dict.get("winner_lifetime_elo_change"),
                match_dict.get("loser_lifetime_elo_change"),
                match_dict.get("winner_went_first"),
                match_dict.get("loser_went_first"),
                match_dict.get("winner_lifetime_elo_after"),
                match_dict.get("loser_lifetime_elo_after"),
                match_dict.get("match_type", "ranked"),
                match_dict.get("voice") or 0,
                archived_at,
                *(match_dict.get(col) for col in AVATAR_MATCH_COLUMN_NAMES),
                match_dict.get("event_k"),
            ),
        )

    # Clear match_records table
    cur_match.execute("DELETE FROM match_records")

    conn_match.commit()
    conn_match.close()

    # Limited format is managed independently via !start_limited_season /
    # !end_limited_season and is deliberately not archived here.

    # Return summary
    if active_event.get("elo_mode") == AVATAR_MODE:
        # The avatar entries stay in event_avatar_standings as this event's archive
        top_players = []
        for row in get_avatar_standings(event_id)[:3]:
            name = row["user_display_name"] or "User#{}".format(row["user_id"])
            top_players.append(("{} ({})".format(name, row["avatar"]), row["event_elo"]))
    else:
        top_players = [(name, elo) for _, name, elo in standings[:3]]
    return {
        "event_id": event_id,
        "event_name": event_name,
        "elo_mode": active_event.get("elo_mode", PLAYER_MODE),
        "total_matches": match_count,
        "total_players": len(standings),
        "top_players": top_players,
    }


# --- Admin Service Functions ---


def recalculate_event_elo() -> dict:
    """Recalculate all event ELO from scratch by replaying match records.

    Replays the season's rated matches in order. Each match is played at the
    lower of the two players' K-factors, and a player's K ramps up with their
    own games (16 for their first game of the season, +2 per game, max 32).
    The K each match used and every player's season game count are rewritten
    along the way. In an Avatar-mode event the avatar entries are rebuilt too.
    Requires an active event.

    Returns:
        dict with keys: event_name, players_reset, matches_replayed, players_updated,
        top_players (list of (name, elo) tuples, up to 5).

    Raises:
        ValueError: If no event is active.
    """
    active_event = get_active_event()
    if not active_event:
        raise ValueError("No active event. Nothing to recalculate.")

    migrate_to_dual_elo_system()
    create_db()
    event_start_str = active_event["start_date"].isoformat()
    event_name = active_event["event_name"]

    match_conn = sqlite3.connect("match_records.db")
    match_cur = match_conn.cursor()
    match_cur.execute(
        f"""
        SELECT rowid, winner_id, losser_id
        FROM match_records
        WHERE timestamp >= ? AND {ELO_COUNTING_MATCH_FILTER}
        ORDER BY timestamp ASC, rowid ASC
        """,
        (event_start_str,),
    )
    matches = match_cur.fetchall()

    # Replay each match at the K its two players had reached
    player_elos: dict[int, int] = {}
    player_games: dict[int, int] = {}
    for rowid, winner_id, loser_id in matches:
        k_value = match_event_k(player_games.get(winner_id, 0), player_games.get(loser_id, 0))
        w_elo = player_elos.get(winner_id, 1500)
        l_elo = player_elos.get(loser_id, 1500)
        w_change, l_change = _calculate_event_changes(w_elo, l_elo, k_value)
        player_elos[winner_id] = w_elo + w_change
        player_elos[loser_id] = l_elo + l_change
        player_games[winner_id] = player_games.get(winner_id, 0) + 1
        player_games[loser_id] = player_games.get(loser_id, 0) + 1
        match_cur.execute("UPDATE match_records SET event_k = ? WHERE rowid = ?", (k_value, rowid))
    match_conn.commit()
    match_conn.close()

    elo_conn = sqlite3.connect("elo.db")
    elo_cur = elo_conn.cursor()
    elo_cur.execute("UPDATE overall_standings SET online_event_elo = 1500, online_event_games = 0")
    players_reset = elo_cur.rowcount
    for user_id, elo_val in player_elos.items():
        elo_cur.execute(
            "UPDATE overall_standings SET online_event_elo = ?, online_event_games = ? WHERE user_id = ?",
            (elo_val, player_games[user_id], user_id),
        )
    elo_conn.commit()

    participant_ids = set(player_elos.keys())
    elo_cur.execute(
        "SELECT user_id, user_display_name, online_event_elo FROM overall_standings "
        "ORDER BY online_event_elo DESC"
    )
    top_players = [(name, elo) for uid, name, elo in elo_cur.fetchall()
                   if uid in participant_ids][:5]
    elo_conn.close()

    if active_event.get("elo_mode") == AVATAR_MODE:
        top_players = _recalculate_avatar_event_elo(active_event)

    logger.info(
        "recalculate_event_elo: %d matches replayed, %d players updated",
        len(matches), len(player_elos),
    )
    return {
        "event_name": event_name,
        "players_reset": players_reset,
        "matches_replayed": len(matches),
        "players_updated": len(player_elos),
        "top_players": top_players,
    }


def _recalculate_avatar_event_elo(active_event) -> list:
    """Rebuild an Avatar-mode event's avatar entries by replaying its matches.

    Replays in order at each match's stored K (recalculate_event_elo has just
    rewritten it), rewriting every match's avatar change/after columns.
    Returns the top 5 entries as (label, elo).
    """
    event_id = active_event["event_id"]
    event_start = active_event["start_date"]
    match_conn = sqlite3.connect("match_records.db")
    match_conn.row_factory = sqlite3.Row
    try:
        matches = match_conn.execute(
            f"""SELECT rowid, winner_id, losser_id, winner_display_name, losser_display_name,
                       timestamp, winner_avatar, loser_avatar, event_k
                FROM match_records
                WHERE timestamp >= ? AND winner_avatar IS NOT NULL AND loser_avatar IS NOT NULL
                  AND {ELO_COUNTING_MATCH_FILTER}
                ORDER BY timestamp ASC, rowid ASC""",
            (event_start.isoformat(),),
        ).fetchall()

        elos: dict[tuple[int, str], int] = {}
        games: dict[tuple[int, str], int] = {}
        names: dict[int, str] = {}
        for m in matches:
            k_value = m["event_k"] or EVENT_K_MAX
            w_key = (m["winner_id"], m["winner_avatar"])
            l_key = (m["losser_id"], m["loser_avatar"])
            w_before, l_before = elos.get(w_key, 1500), elos.get(l_key, 1500)
            w_change, l_change = _calculate_event_changes(w_before, l_before, k_value)
            elos[w_key], elos[l_key] = w_before + w_change, l_before + l_change
            games[w_key] = games.get(w_key, 0) + 1
            games[l_key] = games.get(l_key, 0) + 1
            names[m["winner_id"]] = m["winner_display_name"]
            names[m["losser_id"]] = m["losser_display_name"]
            match_conn.execute(
                "UPDATE match_records SET winner_avatar_elo_change = ?, loser_avatar_elo_change = ?, "
                "winner_avatar_elo_after = ?, loser_avatar_elo_after = ? WHERE rowid = ?",
                (w_change, l_change, elos[w_key], elos[l_key], m["rowid"]),
            )
        match_conn.commit()
    finally:
        match_conn.close()

    elo_conn = sqlite3.connect("elo.db")
    try:
        elo_conn.execute("DELETE FROM event_avatar_standings WHERE event_id = ?", (event_id,))
        elo_conn.executemany(
            "INSERT INTO event_avatar_standings "
            "(event_id, user_id, avatar, user_display_name, event_elo, games_played) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (event_id, user_id, avatar, names.get(user_id), elo, games[(user_id, avatar)])
                for (user_id, avatar), elo in elos.items()
            ],
        )
        elo_conn.commit()
    finally:
        elo_conn.close()

    ranked = sorted(elos.items(), key=lambda item: item[1], reverse=True)[:5]
    return [(f"{names.get(uid) or uid} ({avatar})", elo) for (uid, avatar), elo in ranked]


def get_match_players(match_id: int) -> dict:
    """Get the winner and loser IDs/names for a match.

    Returns:
        dict with keys: winner_id, loser_id, winner_name, loser_name.

    Raises:
        ValueError: If match_id not found.
    """
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT winner_id, losser_id, winner_display_name, losser_display_name FROM match_records WHERE rowid = ?",
        (match_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Match ID #{match_id} not found.")
    return {
        "winner_id": row[0],
        "loser_id": row[1],
        "winner_name": row[2],
        "loser_name": row[3],
    }


_ADMIN_MATCH_COLUMNS = """rowid AS row_id, winner_id, losser_id, winner_display_name, losser_display_name,
       timestamp, match_type, winner_elo_change, loser_elo_change,
       winner_lifetime_elo_change, loser_lifetime_elo_change,
       winner_avatar, loser_avatar, winner_avatar_elo_change, loser_avatar_elo_change, event_k"""


def _load_admin_match_rows(match_cur, where: str, params) -> list[dict]:
    match_cur.execute(f"SELECT {_ADMIN_MATCH_COLUMNS} FROM match_records WHERE {where}", params)
    columns = [d[0] for d in match_cur.description]
    return [dict(zip(columns, row)) for row in match_cur.fetchall()]


def _lifetime_change(row: dict, side: str) -> int:
    """A side's lifetime change; very old rows only stored the event change."""
    lifetime = row[f"{side}_lifetime_elo_change"]
    if lifetime is None:
        lifetime = row[f"{side}_elo_change"]
    return lifetime or 0


def _revert_match_elo(elo_cur, row: dict, avatar_event_id) -> None:
    """Undo one match on every ladder it moved, each by its own change."""
    for side, id_col in (("winner", "winner_id"), ("loser", "losser_id")):
        user_id = row[id_col]
        lifetime = _lifetime_change(row, side)
        event = row[f"{side}_elo_change"] or 0
        if lifetime or event:
            elo_cur.execute(
                "UPDATE overall_standings SET online_elo = online_elo - ?, "
                "online_event_elo = online_event_elo - ? WHERE user_id = ?",
                (lifetime, event, user_id),
            )
        avatar, avatar_change = row[f"{side}_avatar"], row[f"{side}_avatar_elo_change"]
        if avatar_event_id and avatar and avatar_change is not None:
            elo_cur.execute(
                "UPDATE event_avatar_standings SET event_elo = event_elo - ?, "
                "games_played = MAX(games_played - 1, 0) "
                "WHERE event_id = ? AND user_id = ? AND avatar = ?",
                (avatar_change, avatar_event_id, user_id, avatar),
            )


def _current_elos(elo_cur, user_id: int) -> tuple[int, int]:
    elo_cur.execute("SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id = ?", (user_id,))
    row = elo_cur.fetchone()
    return ((row[0] or 1500), (row[1] or 1500)) if row else (1500, 1500)


def _current_avatar_elo(elo_cur, event_id: int, user_id: int, avatar: str) -> int:
    elo_cur.execute(
        "SELECT event_elo FROM event_avatar_standings WHERE event_id = ? AND user_id = ? AND avatar = ?",
        (event_id, user_id, avatar),
    )
    row = elo_cur.fetchone()
    return row[0] if row else 1500


def _replay_match_elo(elo_cur, match_cur, row: dict, active_event, avatar_event_id) -> None:
    """Apply one match again from the players' current ELOs and store the new changes."""
    winner_id, loser_id = row["winner_id"], row["losser_id"]
    # Flipping a result doesn't change how many games anyone had played, so
    # the match keeps the K it was recorded at. Rows from before K was stored
    # fall back to the old day-based value.
    event_k = row.get("event_k")
    if event_k is None:
        match_time = datetime.datetime.fromisoformat(row["timestamp"])
        event_k = (
            _calculate_event_k_value_for_time(active_event["start_date"], match_time)
            if active_event else 32
        )
    w_elo, w_event = _current_elos(elo_cur, winner_id)
    l_elo, l_event = _current_elos(elo_cur, loser_id)
    w_life, w_ev, l_life, l_ev = _calculate_both_elo_changes(w_elo, w_event, l_elo, l_event, event_k)
    for user_id, life, ev in ((winner_id, w_life, w_ev), (loser_id, l_life, l_ev)):
        elo_cur.execute(
            "UPDATE overall_standings SET online_elo = online_elo + ?, "
            "online_event_elo = online_event_elo + ? WHERE user_id = ?",
            (life, ev, user_id),
        )

    w_av_change = l_av_change = w_av_after = l_av_after = None
    w_avatar, l_avatar = row["winner_avatar"], row["loser_avatar"]
    if avatar_event_id and w_avatar and l_avatar:
        w_av = _current_avatar_elo(elo_cur, avatar_event_id, winner_id, w_avatar)
        l_av = _current_avatar_elo(elo_cur, avatar_event_id, loser_id, l_avatar)
        w_av_change, l_av_change = _calculate_event_changes(w_av, l_av, event_k)
        w_av_after, l_av_after = w_av + w_av_change, l_av + l_av_change
        for user_id, avatar, after, name in (
            (winner_id, w_avatar, w_av_after, row["winner_display_name"]),
            (loser_id, l_avatar, l_av_after, row["losser_display_name"]),
        ):
            elo_cur.execute(
                """INSERT INTO event_avatar_standings
                       (event_id, user_id, avatar, user_display_name, event_elo, games_played)
                   VALUES (?, ?, ?, ?, ?, 1)
                   ON CONFLICT (event_id, user_id, avatar) DO UPDATE SET
                       event_elo = excluded.event_elo, games_played = games_played + 1""",
                (avatar_event_id, user_id, avatar, name, after),
            )

    match_cur.execute(
        """UPDATE match_records
           SET winner_elo_change = ?, loser_elo_change = ?,
               winner_lifetime_elo_change = ?, loser_lifetime_elo_change = ?,
               winner_lifetime_elo_after = ?, loser_lifetime_elo_after = ?,
               winner_avatar_elo_change = ?, loser_avatar_elo_change = ?,
               winner_avatar_elo_after = ?, loser_avatar_elo_after = ?
           WHERE rowid = ?""",
        (w_ev, l_ev, w_life, l_life, w_elo + w_life, l_elo + l_life,
         w_av_change, l_av_change, w_av_after, l_av_after, row["row_id"]),
    )
    row.update(
        winner_elo_change=w_ev, loser_elo_change=l_ev,
        winner_lifetime_elo_change=w_life, loser_lifetime_elo_change=l_life,
    )


def _avatar_event_id(active_event):
    create_db()  # admin paths select the avatar columns; make sure they exist first
    if active_event and active_event.get("elo_mode") == AVATAR_MODE:
        return active_event["event_id"]
    return None


def correct_match_record(match_id: int) -> dict:
    """Flip winner/loser of a match and cascade-recalculate all subsequent ELO.

    Every ladder the match moved (lifetime, event, and in Avatar mode the two
    avatar entries) is reverted by its own recorded change, then the flipped
    match and every later rated match of either player is replayed. Avatars
    swap with their players.

    Returns:
        dict with keys: match_id, original_winner_name, original_loser_name,
        new_winner_name, new_loser_name, new_winner_elo_change, new_loser_elo_change,
        recalculated_count, affected_players (set of user_ids).

    Raises:
        ValueError: If match_id not found.
    """
    active_event = get_active_event()
    avatar_event_id = _avatar_event_id(active_event)

    elo_conn = sqlite3.connect("elo.db")
    elo_cur = elo_conn.cursor()
    match_conn = sqlite3.connect("match_records.db")
    match_cur = match_conn.cursor()

    try:
        rows = _load_admin_match_rows(match_cur, "rowid = ?", (match_id,))
        if not rows:
            raise ValueError(f"Match ID #{match_id} not found.")
        target = rows[0]
        rated = target["match_type"] not in NON_ELO_MATCH_TYPES

        orig_winner_id, orig_loser_id = target["winner_id"], target["losser_id"]
        orig_winner_name, orig_loser_name = target["winner_display_name"], target["losser_display_name"]

        # Later rated matches of either player are replayed on top of the fix
        subsequent = []
        if rated:
            subsequent = _load_admin_match_rows(
                match_cur,
                f"""timestamp > ? AND (winner_id IN (?, ?) OR losser_id IN (?, ?))
                    AND (match_type IS NULL OR match_type NOT IN ({NON_ELO_MATCH_TYPES_SQL}))
                    ORDER BY timestamp ASC""",
                (target["timestamp"], orig_winner_id, orig_loser_id, orig_winner_id, orig_loser_id),
            )
        affected_players = {orig_winner_id, orig_loser_id}
        for m in subsequent:
            affected_players.update((m["winner_id"], m["losser_id"]))

        if rated:
            for m in reversed(subsequent):
                _revert_match_elo(elo_cur, m, avatar_event_id)
            _revert_match_elo(elo_cur, target, avatar_event_id)

        # Flip the target match (players, their decks and their avatars)
        match_cur.execute(
            """UPDATE match_records
               SET winner_id = losser_id, losser_id = winner_id,
                   winner_display_name = losser_display_name, losser_display_name = winner_display_name,
                   curiosa_url = curiosa_url_loser,
                   curiosa_url_winner = curiosa_url_loser, curiosa_url_loser = curiosa_url_winner,
                   json_deck_data_winner = json_deck_data_loser, json_deck_data_loser = json_deck_data_winner,
                   winner_avatar = loser_avatar, loser_avatar = winner_avatar
               WHERE rowid = ?""",
            (match_id,),
        )
        flipped = _load_admin_match_rows(match_cur, "rowid = ?", (match_id,))[0]

        new_w_change = new_l_change = 0
        recalculated = 0
        if rated:
            _replay_match_elo(elo_cur, match_cur, flipped, active_event, avatar_event_id)
            new_w_change, new_l_change = flipped["winner_elo_change"], flipped["loser_elo_change"]
            for m in subsequent:
                _replay_match_elo(elo_cur, match_cur, m, active_event, avatar_event_id)
                recalculated += 1

        elo_conn.commit()
        match_conn.commit()
    except Exception:
        elo_conn.rollback()
        match_conn.rollback()
        raise
    finally:
        elo_conn.close()
        match_conn.close()

    logger.info(
        "correct_match_record: match #%d flipped (%s -> %s), %d subsequent matches recalculated",
        match_id, orig_winner_name, orig_loser_name, recalculated,
    )
    return {
        "match_id": match_id,
        "original_winner_name": orig_winner_name,
        "original_loser_name": orig_loser_name,
        "new_winner_name": orig_loser_name,
        "new_loser_name": orig_winner_name,
        "new_winner_elo_change": new_w_change,
        "new_loser_elo_change": new_l_change,
        "recalculated_count": recalculated,
        "affected_players": affected_players,
    }


def remove_match_record(match_id: int) -> dict:
    """Revert ELO changes for a match and delete its record.

    Returns:
        dict with keys: match_id, winner_name, loser_name, timestamp, reverted_info (list of str).

    Raises:
        ValueError: If match_id not found.
    """
    avatar_event_id = _avatar_event_id(get_active_event())

    elo_conn = sqlite3.connect("elo.db")
    elo_cur = elo_conn.cursor()
    match_conn = sqlite3.connect("match_records.db")
    match_cur = match_conn.cursor()

    try:
        rows = _load_admin_match_rows(match_cur, "rowid = ?", (match_id,))
        if not rows:
            raise ValueError(f"Match ID #{match_id} not found.")
        match = rows[0]
        _revert_match_elo(elo_cur, match, avatar_event_id)
        if match["event_k"] is not None:
            # A rated season game: both players have one game fewer toward their K ramp
            elo_cur.execute(
                "UPDATE overall_standings SET online_event_games = MAX(COALESCE(online_event_games, 0) - 1, 0) "
                "WHERE user_id IN (?, ?)",
                (match["winner_id"], match["losser_id"]),
            )

        reverted_info = []
        for side, name_col, sign in (("winner", "winner_display_name", -1), ("loser", "losser_display_name", 1)):
            lifetime = _lifetime_change(match, side)
            event = match[f"{side}_elo_change"] or 0
            if not (lifetime or event):
                continue
            text = f"**{match[name_col]}**: Lifetime {sign * abs(lifetime):+d}, Event {sign * abs(event):+d} ELO"
            avatar_change = match[f"{side}_avatar_elo_change"]
            if avatar_event_id and match[f"{side}_avatar"] and avatar_change is not None:
                text += f", {match[f'{side}_avatar']} {-avatar_change:+d}"
            reverted_info.append(text)

        match_cur.execute("DELETE FROM match_records WHERE rowid = ?", (match_id,))
        elo_conn.commit()
        match_conn.commit()
    except Exception:
        elo_conn.rollback()
        match_conn.rollback()
        raise
    finally:
        elo_conn.close()
        match_conn.close()

    winner_name, loser_name = match["winner_display_name"], match["losser_display_name"]
    logger.info("remove_match_record: removed match #%d (%s vs %s)", match_id, winner_name, loser_name)
    return {
        "match_id": match_id,
        "winner_name": winner_name,
        "loser_name": loser_name,
        "timestamp": match["timestamp"],
        "reverted_info": reverted_info,
    }


def remove_player(user_id: int, user_name: str) -> dict:
    """Remove a player and revert all ELO changes from their matches.

    Opponents get back what each match moved on each ladder: lifetime by the
    lifetime change, event by the event change, and avatar entries by the
    avatar change.

    Returns:
        dict with keys: matches_deleted, player_removed (bool),
        adjustments_made (list of str), elo_adjustments (dict).

    Raises:
        ValueError: If no matches found for the player.
    """
    avatar_event_id = _avatar_event_id(get_active_event())

    elo_conn = sqlite3.connect("elo.db")
    elo_cur = elo_conn.cursor()
    match_conn = sqlite3.connect("match_records.db")
    match_cur = match_conn.cursor()

    try:
        matches = _load_admin_match_rows(match_cur, "winner_id = ? OR losser_id = ?", (user_id, user_id))
        if not matches:
            raise ValueError(f"No matches found for {user_name}.")

        # Per opponent: (lifetime, event, name) adjustment; avatar entries apply directly
        elo_adjustments: dict[int, tuple[int, str]] = {}
        lifetime_adjustments: dict[int, int] = {}
        for m in matches:
            opp_side = "loser" if m["winner_id"] == user_id else "winner"
            opp_id = m["losser_id"] if opp_side == "loser" else m["winner_id"]
            opp_name = m["losser_display_name"] if opp_side == "loser" else m["winner_display_name"]
            if not opp_id:
                continue
            event = m[f"{opp_side}_elo_change"] or 0
            lifetime = _lifetime_change(m, opp_side)
            adj, name = elo_adjustments.get(opp_id, (0, opp_name))
            elo_adjustments[opp_id] = (adj - event, name)
            lifetime_adjustments[opp_id] = lifetime_adjustments.get(opp_id, 0) - lifetime
            if m["event_k"] is not None:
                elo_cur.execute(
                    "UPDATE overall_standings SET online_event_games = "
                    "MAX(COALESCE(online_event_games, 0) - 1, 0) WHERE user_id = ?",
                    (opp_id,),
                )

            avatar, avatar_change = m[f"{opp_side}_avatar"], m[f"{opp_side}_avatar_elo_change"]
            if avatar_event_id and avatar and avatar_change is not None:
                elo_cur.execute(
                    "UPDATE event_avatar_standings SET event_elo = event_elo - ?, "
                    "games_played = MAX(games_played - 1, 0) "
                    "WHERE event_id = ? AND user_id = ? AND avatar = ?",
                    (avatar_change, avatar_event_id, opp_id, avatar),
                )

        adjustments_made = []
        for opp_id, (event_adj, opp_name) in elo_adjustments.items():
            lifetime_adj = lifetime_adjustments.get(opp_id, 0)
            if event_adj or lifetime_adj:
                elo_cur.execute(
                    "UPDATE overall_standings SET online_elo = online_elo + ?, "
                    "online_event_elo = online_event_elo + ? WHERE user_id = ?",
                    (lifetime_adj, event_adj, opp_id),
                )
                adjustments_made.append(f"{opp_name}: {event_adj:+d}")

        match_cur.execute(
            "DELETE FROM match_records WHERE winner_id = ? OR losser_id = ?",
            (user_id, user_id),
        )
        matches_deleted = match_cur.rowcount

        elo_cur.execute("DELETE FROM overall_standings WHERE user_id = ?", (user_id,))
        player_removed = elo_cur.rowcount > 0
        if avatar_event_id:
            elo_cur.execute(
                "DELETE FROM event_avatar_standings WHERE user_id = ? AND event_id = ?",
                (user_id, avatar_event_id),
            )

        elo_conn.commit()
        match_conn.commit()
    except Exception:
        elo_conn.rollback()
        match_conn.rollback()
        raise
    finally:
        elo_conn.close()
        match_conn.close()

    logger.info(
        "remove_player: removed %s (id=%s), %d matches deleted, %d opponents adjusted",
        user_name, user_id, matches_deleted, len(adjustments_made),
    )
    return {
        "matches_deleted": matches_deleted,
        "player_removed": player_removed,
        "adjustments_made": adjustments_made,
        "elo_adjustments": elo_adjustments,
    }


# --- Milestone & Solo Reports ---


def check_milestone(match_id):
    """
    Check if the current match is a milestone (every 100 matches).

    Args:
        match_id: The ID of the just-recorded match

    Returns:
        int or None: The milestone number if this is a milestone match, None otherwise
    """
    total_matches = get_total_match_count()
    if total_matches > 0 and total_matches % 100 == 0:
        return total_matches
    return None


async def solo_match_report(
    reporter_id: int,
    reporter_global: str,
    opponent_name: str,
    is_winner: bool,
    first_player: str,
    match_time: int,
    curiosa_link: str,
    match_comment: str,
) -> int:
    """
    Save a solo match report to the database.

    Args:
        reporter_id: Discord ID of the reporting player
        reporter_global: Global name of the reporting player
        opponent_name: Name of the opponent (manually entered)
        is_winner: True if reporter won, False if lost
        first_player: 'y' if reporter went first, 'n' if not
        match_time: Duration of match in minutes
        curiosa_link: URL to Curiosa deck
        match_comment: Additional match notes

    Returns:
        The report_id of the newly created report
    """
    logger.info(f"Logging solo match report for user {reporter_global}")
    create_db()  # Ensure tables exist
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    json_deck_data = "{}"
    if curiosa_link and curiosa_link != "No URL provided":
        json_deck_data = scrape_Curosa(curiosa_link, "deck_data_test.json")

    cur.execute(
        """INSERT INTO solo_match_reports
           (reporter_id, reporter_name, opponent_name, is_winner,
            first_player, match_time, curiosa_link, match_comment,
            report_date, json_deck_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
        (
            reporter_id,
            reporter_global,
            opponent_name,
            is_winner,
            first_player,
            match_time,
            curiosa_link,
            match_comment,
            json_deck_data,
        ),
    )

    report_id = cur.lastrowid
    conn.commit()
    conn.close()

    return report_id


def correct_limited_match_record(match_id: int) -> dict:
    """Flip winner/loser of a limited match and recalculate ELO.

    Returns:
        dict with keys: match_id, original_winner_name, original_loser_name,
        new_winner_name, new_loser_name, new_winner_elo_change, new_loser_elo_change.

    Raises:
        ValueError: If match_id not found.
    """
    elo_conn = sqlite3.connect("elo.db")
    elo_cur = elo_conn.cursor()
    match_conn = sqlite3.connect("match_records.db")
    match_cur = match_conn.cursor()

    match_cur.execute(
        """SELECT match_id, winner_id, loser_id, winner_display_name, loser_display_name,
                  timestamp, winner_elo_change, loser_elo_change,
                  winner_run_id, loser_run_id
           FROM limited_match_records WHERE match_id = ?""",
        (match_id,),
    )
    target = match_cur.fetchone()
    if not target:
        elo_conn.close()
        match_conn.close()
        raise ValueError(f"Limited match ID #{match_id} not found.")

    (_, orig_winner_id, orig_loser_id, orig_winner_name, orig_loser_name,
     target_ts, target_w_change, target_l_change,
     winner_run_id, loser_run_id) = target

    # Revert ELO for target match
    if target_w_change:
        elo_cur.execute(
            "UPDATE limited_elo SET elo = elo - ? WHERE user_id = ?",
            (target_w_change, orig_winner_id),
        )
    if target_l_change:
        elo_cur.execute(
            "UPDATE limited_elo SET elo = elo - ? WHERE user_id = ?",
            (target_l_change, orig_loser_id),
        )
    elo_conn.commit()

    # Flip the target match
    new_winner_id, new_winner_name = orig_loser_id, orig_loser_name
    new_loser_id, new_loser_name = orig_winner_id, orig_winner_name

    # Recalculate ELO for the corrected match
    elo_cur.execute("SELECT elo FROM limited_elo WHERE user_id = ?", (new_winner_id,))
    row = elo_cur.fetchone()
    nw_elo = (row[0] or 1500) if row else 1500

    elo_cur.execute("SELECT elo FROM limited_elo WHERE user_id = ?", (new_loser_id,))
    row = elo_cur.fetchone()
    nl_elo = (row[0] or 1500) if row else 1500

    nw_elo_after = update_elo(nw_elo, nl_elo, True)
    nl_elo_after = update_elo(nl_elo, nw_elo, False)
    new_w_change = nw_elo_after - nw_elo
    new_l_change = nl_elo_after - nl_elo

    elo_cur.execute(
        "UPDATE limited_elo SET elo = ? WHERE user_id = ?",
        (nw_elo_after, new_winner_id),
    )
    elo_cur.execute(
        "UPDATE limited_elo SET elo = ? WHERE user_id = ?",
        (nl_elo_after, new_loser_id),
    )

    # Update arena run records
    if winner_run_id:
        match_cur.execute(
            "SELECT wins, losses FROM limited_arena_runs WHERE run_id = ?",
            (winner_run_id,),
        )
        run_row = match_cur.fetchone()
        if run_row:
            wins, losses = run_row
            match_cur.execute(
                "UPDATE limited_arena_runs SET wins = ? WHERE run_id = ?",
                (max(0, wins - 1), winner_run_id),
            )

    if loser_run_id:
        match_cur.execute(
            "SELECT wins, losses FROM limited_arena_runs WHERE run_id = ?",
            (loser_run_id,),
        )
        run_row = match_cur.fetchone()
        if run_row:
            wins, losses = run_row
            match_cur.execute(
                "UPDATE limited_arena_runs SET losses = ? WHERE run_id = ?",
                (max(0, losses - 1), loser_run_id),
            )

    # Update the match record with flipped winner/loser
    match_cur.execute(
        """UPDATE limited_match_records
           SET winner_id = ?, winner_display_name = ?,
               loser_id = ?, loser_display_name = ?,
               winner_elo_change = ?, loser_elo_change = ?,
               winner_run_id = ?, loser_run_id = ?
           WHERE match_id = ?""",
        (new_winner_id, new_winner_name, new_loser_id, new_loser_name,
         new_w_change, new_l_change,
         loser_run_id, winner_run_id,
         match_id),
    )

    elo_conn.commit()
    match_conn.commit()
    elo_conn.close()
    match_conn.close()

    logger.info(
        "correct_limited_match_record: match #%d flipped (%s -> %s)",
        match_id, orig_winner_name, new_winner_name,
    )
    return {
        "match_id": match_id,
        "original_winner_name": orig_winner_name,
        "original_loser_name": orig_loser_name,
        "new_winner_name": new_winner_name,
        "new_loser_name": new_loser_name,
        "new_winner_elo_change": new_w_change,
        "new_loser_elo_change": new_l_change,
    }
