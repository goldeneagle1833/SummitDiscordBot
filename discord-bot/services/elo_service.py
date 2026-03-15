"""Business logic for ELO calculations, match reporting, and event management."""

import sqlite3
import datetime
import logging

from utils.deck_checker import scrape_Curosa
from repositories.elo_repo import (
    create_db,
    create_events_table,
    create_match_records_archive,
    ensure_event_elo_column,
    migrate_to_dual_elo_system,
    get_active_event,
    get_total_match_count,
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


def calculate_event_k_value(start_date):
    """
    Calculate K-value based on days since event started.

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

    cur.execute("""CREATE TABLE IF NOT EXISTS overall_standings
                   (user_id INTEGER PRIMARY KEY,
                    user_display_name TEXT,
                    elo INTEGER DEFAULT 1500,
                    event_elo INTEGER DEFAULT 1500,
                    paper_elo INTEGER DEFAULT 1500,
                    online_elo INTEGER DEFAULT 1500,
                    paper_event_elo INTEGER DEFAULT 1500,
                    online_event_elo INTEGER DEFAULT 1500
                   )""")

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

    # Update player's online ELOs (also update legacy elo/event_elo for backwards compat)
    cur.execute(
        "UPDATE overall_standings SET online_elo = ?, online_event_elo = ?, elo = ?, event_elo = ? WHERE user_id = ?",
        (new_online_elo, new_online_event_elo, new_online_elo, new_online_event_elo, user_id),
    )

    conn.commit()
    conn.close()

    return (new_online_elo, online_change, new_online_event_elo, online_event_change, True)


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

    cur.execute("""CREATE TABLE IF NOT EXISTS overall_standings
                   (user_id INTEGER PRIMARY KEY,
                    user_display_name TEXT,
                    elo INTEGER DEFAULT 1500,
                    event_elo INTEGER DEFAULT 1500,
                    paper_elo INTEGER DEFAULT 1500,
                    online_elo INTEGER DEFAULT 1500,
                    paper_event_elo INTEGER DEFAULT 1500,
                    online_event_elo INTEGER DEFAULT 1500
                   )""")

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

    # Update player's online ELOs (also update legacy elo/event_elo for backwards compat)
    cur.execute(
        "UPDATE overall_standings SET online_elo = ?, online_event_elo = ?, elo = ?, event_elo = ? WHERE user_id = ?",
        (new_online_elo, new_online_event_elo, new_online_elo, new_online_event_elo, user_id),
    )

    conn.commit()
    conn.close()

    return (new_online_elo, online_change, new_online_event_elo, online_event_change, True)


# --- Match Reporting ---


async def winner_report(
    reporter_id,
    user_id,
    user_display_name,
    did_win,
    opponent_id,
    opponent_display_name,
    first_player,
    match_time,
    curiosa_link,
    match_comment,
    interaction_user_id,
    interaction_global,
    winner_deck_url=None,
    loser_deck_url=None,
    winner_went_first=None,
    loser_went_first=None,
    match_type="ranked",
):
    """
    Log a win in the database.

    Returns:
        Tuple of (match_id, winner_id, loser_id, event_active)
        event_active is True if ELO was updated, False if no active event
    """
    logger.info(f"Logging win for user {interaction_global} (match_type={match_type})")
    create_db()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Fetch deck data for both players
    json_deck_data_winner = "{}"
    json_deck_data_loser = "{}"

    # Use new deck URLs if provided, otherwise fall back to old curiosa_link
    if winner_deck_url:
        json_deck_data_winner = scrape_Curosa(winner_deck_url, "deck_data_test.json")
    elif curiosa_link and curiosa_link != "No URL provided":
        # Backward compatibility: if only one URL provided, assume it's winner's
        json_deck_data_winner = scrape_Curosa(curiosa_link, "deck_data_test.json")

    if loser_deck_url:
        json_deck_data_loser = scrape_Curosa(loser_deck_url, "deck_data_test.json")

    # Skip ELO updates for testing matches
    if match_type == "testing":
        winner_elo_change = 0
        loser_elo_change = 0
        winner_lifetime_elo_change = 0
        loser_lifetime_elo_change = 0
        event_active = False
    else:
        # Update ELO and get the change values
        new_lifetime_elo, lifetime_change, new_event_elo, event_change, event_active = (
            update_elo_db(interaction_user_id, interaction_global, did_win, opponent_id)
        )
        # Store both lifetime and event ELO changes
        winner_lifetime_elo_change = lifetime_change
        winner_elo_change = event_change if event_active else 0
        # Approximate loser changes (negative of winner's)
        loser_lifetime_elo_change = -lifetime_change
        loser_elo_change = (
            -event_change if event_active else 0
        )

    cur.execute(
        "INSERT INTO match_records (reporter_id, winner_id, winner_display_name, "
        "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
        "curiosa_url, curiosa_url_winner, curiosa_url_loser, match_comment, "
        "json_deck_data, json_deck_data_winner, json_deck_data_loser, winner_elo_change, loser_elo_change, "
        "winner_lifetime_elo_change, loser_lifetime_elo_change, "
        "winner_went_first, loser_went_first, match_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            reporter_id,
            user_id,
            user_display_name,
            opponent_id,
            opponent_display_name,
            did_win,
            datetime.datetime.now().isoformat(),
            first_player,
            match_time,
            curiosa_link,  # Keep for backward compatibility
            winner_deck_url or curiosa_link,
            loser_deck_url,
            match_comment,
            json_deck_data_winner,  # Keep for backward compatibility
            json_deck_data_winner,
            json_deck_data_loser,
            winner_elo_change,
            loser_elo_change,
            winner_lifetime_elo_change,
            loser_lifetime_elo_change,
            winner_went_first,
            loser_went_first,
            match_type,
        ),
    )

    match_id = cur.lastrowid
    conn.commit()
    conn.close()

    return (match_id, user_id, opponent_id, event_active)


async def losser_report(
    reporter_id,
    user_id,
    user_display_name,
    did_win,
    opponent_id,
    opponent_display_name,
    first_player,
    match_time,
    curiosa_link,
    match_comment,
    interaction_user_id,
    interaction_global,
    winner_deck_url=None,
    loser_deck_url=None,
    winner_went_first=None,
    loser_went_first=None,
    match_type="ranked",
):
    """
    Log a loss in the database.

    Returns:
        Tuple of (match_id, winner_id, loser_id, event_active)
        event_active is True if ELO was updated, False if no active event
    """
    logger.info(f"Logging loss for user {interaction_global}")
    create_db()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Fetch deck data for both players
    json_deck_data_winner = "{}"
    json_deck_data_loser = "{}"

    # Use new deck URLs if provided, otherwise fall back to old curiosa_link
    if winner_deck_url:
        json_deck_data_winner = scrape_Curosa(winner_deck_url, "deck_data_test.json")

    if loser_deck_url:
        json_deck_data_loser = scrape_Curosa(loser_deck_url, "deck_data_test.json")
    elif curiosa_link and curiosa_link != "No URL provided":
        # Backward compatibility: if only one URL provided, assume it's loser's
        json_deck_data_loser = scrape_Curosa(curiosa_link, "deck_data_test.json")

    # Update ELO and get the change values
    new_lifetime_elo, lifetime_change, new_event_elo, event_change, event_active = (
        update_elo_db(interaction_user_id, interaction_global, did_win, opponent_id)
    )
    # Store both lifetime and event ELO changes
    loser_lifetime_elo_change = lifetime_change
    loser_elo_change = event_change if event_active else 0
    # Approximate winner changes (negative of loser's)
    winner_lifetime_elo_change = -lifetime_change
    winner_elo_change = (
        -event_change if event_active else 0
    )

    cur.execute(
        "INSERT INTO match_records (reporter_id, winner_id, winner_display_name, "
        "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
        "curiosa_url, curiosa_url_winner, curiosa_url_loser, match_comment, "
        "json_deck_data, json_deck_data_winner, json_deck_data_loser, winner_elo_change, loser_elo_change, "
        "winner_lifetime_elo_change, loser_lifetime_elo_change, "
        "winner_went_first, loser_went_first, match_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            reporter_id,
            user_id,
            user_display_name,
            opponent_id,
            opponent_display_name,
            did_win,
            datetime.datetime.now().isoformat(),
            first_player,
            match_time,
            curiosa_link,  # Keep for backward compatibility
            winner_deck_url,
            loser_deck_url or curiosa_link,
            match_comment,
            json_deck_data_loser,  # Keep for backward compatibility
            json_deck_data_winner,
            json_deck_data_loser,
            winner_elo_change,
            loser_elo_change,
            winner_lifetime_elo_change,
            loser_lifetime_elo_change,
            winner_went_first,
            loser_went_first,
            match_type,
        ),
    )

    match_id = cur.lastrowid
    conn.commit()
    conn.close()

    return (match_id, user_id, opponent_id, event_active)


# --- Event Management ---


def start_new_event(event_name):
    """
    Start a new event, archiving any active event first.

    Args:
        event_name: Name for the new event

    Returns:
        dict with new event info and optional previous event summary
    """
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
        "INSERT INTO events (event_name, start_date, is_active) VALUES (?, ?, 1)",
        (event_name, start_date),
    )
    event_id = cur.lastrowid

    # Reset all players' event ELOs to 1500 (both paper and online)
    cur.execute("UPDATE overall_standings SET event_elo = 1500, paper_event_elo = 1500, online_event_elo = 1500")

    conn.commit()
    conn.close()

    return {
        "event_id": event_id,
        "event_name": event_name,
        "start_date": datetime.datetime.fromisoformat(start_date),
        "previous_event": previous_event_summary,
    }


def end_current_event():
    """
    End the current active event and archive its data.

    Returns:
        dict with event summary (top players, total matches) or None
    """
    active_event = get_active_event()
    if not active_event:
        return None

    event_id = active_event["event_id"]
    event_name = active_event["event_name"]

    # Archive standings
    conn_elo = sqlite3.connect("elo.db")
    cur_elo = conn_elo.cursor()

    # Get all players with either paper or online event games (event_elo != 1500)
    cur_elo.execute("""SELECT user_id, user_display_name, paper_event_elo, online_event_elo
                       FROM overall_standings
                       WHERE paper_event_elo != 1500 OR online_event_elo != 1500""")
    all_players = cur_elo.fetchall()

    # Build separate rankings for paper and online
    paper_standings = [(uid, name, paper_elo) for uid, name, paper_elo, _ in all_players if paper_elo != 1500]
    online_standings = [(uid, name, online_elo) for uid, name, _, online_elo in all_players if online_elo != 1500]

    # Sort by ELO descending
    paper_standings.sort(key=lambda x: x[2], reverse=True)
    online_standings.sort(key=lambda x: x[2], reverse=True)

    # Build combined standings using max(paper_elo, online_elo) for each player
    standings = [(uid, name, max(paper_elo, online_elo)) for uid, name, paper_elo, online_elo in all_players]
    standings.sort(key=lambda x: x[2], reverse=True)

    # Create rank maps
    paper_ranks = {uid: rank for rank, (uid, _, _) in enumerate(paper_standings, start=1)}
    online_ranks = {uid: rank for rank, (uid, _, _) in enumerate(online_standings, start=1)}

    # Archive combined standings (one row per player with both paper and online data)
    archived_at = datetime.datetime.now().isoformat()
    for user_id, display_name, paper_elo, online_elo in all_players:
        # Legacy event_elo = max of paper and online
        final_event_elo = max(paper_elo, online_elo)
        # Rank by whichever ELO is higher
        if paper_elo > online_elo:
            final_rank = paper_ranks.get(user_id, 0)
        else:
            final_rank = online_ranks.get(user_id, 0)

        cur_elo.execute(
            """INSERT INTO event_standings_archive
               (event_id, user_id, user_display_name, final_event_elo, final_rank,
                final_paper_event_elo, final_paper_rank, final_online_event_elo, final_online_rank, archived_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, user_id, display_name, final_event_elo, final_rank,
             paper_elo, paper_ranks.get(user_id, None), online_elo, online_ranks.get(user_id, None), archived_at),
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
                winner_elo_change, loser_elo_change, archived_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                archived_at,
            ),
        )

    # Clear match_records table
    cur_match.execute("DELETE FROM match_records")

    conn_match.commit()
    conn_match.close()

    # Return summary
    top_3 = standings[:3] if len(standings) >= 3 else standings
    return {
        "event_id": event_id,
        "event_name": event_name,
        "total_matches": match_count,
        "total_players": len(standings),
        "top_players": [(name, elo) for _, name, elo in top_3],
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
