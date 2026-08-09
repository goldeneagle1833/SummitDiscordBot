"""Business logic for Limited queue (arena draft mode).

Handles arena run management, limited ELO updates, match reporting,
forfeit penalty calculation, and run lifecycle.
"""

import logging

from services.elo_service import update_elo
from repositories.elo_repo import get_active_event
from utils.deck_checker import scrape_Curosa
from repositories.limited_repo import (
    get_limited_elo,
    upsert_limited_elo,
    create_arena_run as _create_arena_run,
    get_active_arena_run,
    get_arena_run,
    update_arena_run_record,
    complete_arena_run,
    close_all_active_runs,
    insert_limited_match_record,
    archive_limited_standings,
    archive_limited_matches,
    archive_limited_arena_runs,
    reset_limited_elo_to_default,
)

logger = logging.getLogger("discord_bot")

MAX_ARENA_WINS = 4
MAX_ARENA_LOSSES = 2

# --- Limited ELO ---


def update_limited_elo(user_id: int, display_name: str, did_win: bool, opponent_id: int):
    """Update Limited ELO for a player after a match.

    Uses constant K=32. Completely separate from main ELO system.

    Returns:
        Tuple of (new_elo, elo_change)
    """
    player_elo = get_limited_elo(user_id)
    opponent_elo = get_limited_elo(opponent_id)

    new_elo = update_elo(player_elo, opponent_elo, did_win, k=32)
    elo_change = new_elo - player_elo

    upsert_limited_elo(user_id, display_name, new_elo, elo_change=elo_change)

    logger.info(
        "Limited ELO update for %s: %d -> %d (%+d)",
        user_id, player_elo, new_elo, elo_change,
    )
    return (new_elo, elo_change)


# --- Arena Run Management ---


def start_arena_run(user_id: int, display_name: str, deck_url: str) -> dict:
    """Start a new arena run for a player.

    Checks for existing active run (error if one exists).
    Raises ValueError if no active event (between seasons).
    Records starting ELO and scrapes deck data.

    Returns:
        dict with run info (run_id, wins, losses, deck_url, starting_elo, etc.)
    """
    if not get_active_event():
        raise ValueError("No active event — arena runs cannot be started between seasons.")

    active = get_active_arena_run(user_id)
    if active:
        raise ValueError(f"User {user_id} already has an active arena run (run_id={active['run_id']})")

    starting_elo = get_limited_elo(user_id)

    # Scrape deck data (best-effort, don't fail the run if scraping fails)
    json_deck_data = "{}"
    try:
        if deck_url:
            json_deck_data = scrape_Curosa(deck_url, "deck_data_test.json")
    except Exception as e:
        logger.warning("Failed to scrape deck data for arena run: %s", e)

    run_id = _create_arena_run(user_id, display_name, deck_url, json_deck_data, starting_elo)
    run = get_arena_run(run_id)
    if run is None:
        raise RuntimeError(f"Failed to load arena run {run_id} after creation")

    return run


def check_run_complete(run_id: int) -> bool:
    """Check if an arena run has reached completion (2L or 4W).

    Auto-completes the run if thresholds are met.

    Returns:
        True if run is now complete, False if still active.
    """
    run = get_arena_run(run_id)
    if not run or run["status"] != "active":
        return run is not None and run["status"] != "active"

    if run["wins"] >= MAX_ARENA_WINS or run["losses"] >= MAX_ARENA_LOSSES:
        complete_arena_run(run_id, "completed")
        logger.info(
            "Arena run %d completed: %d-%d",
            run_id, run["wins"], run["losses"],
        )
        return True

    return False


def get_run_summary(run_id: int, last_match_elo_change: int = None) -> str:
    """Get a formatted summary of an arena run for DM display.

    Args:
        run_id: The arena run ID.
        last_match_elo_change: If provided, shows the per-match ELO change
            in addition to the cumulative run change.

    Returns:
        Formatted string with record, deck URL, ELO, and status.
    """
    run = get_arena_run(run_id)
    if not run:
        return "Arena run not found."

    current_elo = get_limited_elo(run["user_id"])
    run_elo_change = current_elo - run["starting_elo"]
    run_sign = "+" if run_elo_change >= 0 else ""

    status_label = {
        "active": "In Progress",
        "completed": "Completed",
        "forfeited": "Forfeited",
        "closed": "Closed",
    }.get(run["status"], run["status"])

    # Show per-match change if provided, plus cumulative run change
    if last_match_elo_change is not None:
        match_sign = "+" if last_match_elo_change >= 0 else ""
        elo_line = (
            f"This match: **{match_sign}{last_match_elo_change}** | "
            f"Run total: **{run_sign}{run_elo_change}**\n"
            f"Limited ELO: **{current_elo}**"
        )
    else:
        elo_line = f"Limited ELO: **{current_elo}** ({run_sign}{run_elo_change})"

    return (
        f"**Limited Arena Run** - {status_label}\n"
        f"Record: **{run['wins']}-{run['losses']}**\n"
        f"Deck: {run['deck_url']}\n"
        f"{elo_line}\n"
        f"Started: {run['created_at'][:10]}"
    )


def limited_winner_report(
    reporter_id: int,
    winner_id: int,
    winner_display_name: str,
    loser_id: int,
    loser_display_name: str,
    first_player: str,
    match_time: int,
    curiosa_url_winner: str,
    curiosa_url_loser: str,
    match_comment: str,
    winner_went_first: str,
    loser_went_first: str,
    winner_run_id: int,
    loser_run_id: int,
    json_deck_data_winner: str = "{}",
    json_deck_data_loser: str = "{}",
) -> tuple:
    """Report a limited match from the winner's perspective.

    Updates limited ELO for both players, inserts a limited match record,
    and increments arena run records.

    ELO is only updated when an active event exists (skipped between seasons).

    Returns:
        Tuple of (match_id, winner_run_complete, loser_run_complete, winner_elo_change, loser_elo_change)
    """
    event_active = bool(get_active_event())

    # Update Limited ELO for both players (skip between seasons)
    winner_elo_change = 0
    loser_elo_change = 0
    if event_active:
        _, winner_elo_change = update_limited_elo(winner_id, winner_display_name, True, loser_id)
        _, loser_elo_change = update_limited_elo(loser_id, loser_display_name, False, winner_id)
    else:
        logger.info("No active event — limited match recorded without ELO changes")

    # Insert limited match record
    match_id = insert_limited_match_record(
        reporter_id=reporter_id,
        winner_id=winner_id,
        winner_display_name=winner_display_name,
        loser_id=loser_id,
        loser_display_name=loser_display_name,
        did_win=True,
        first_player=first_player,
        match_time=match_time,
        curiosa_url_winner=curiosa_url_winner,
        curiosa_url_loser=curiosa_url_loser,
        match_comment=match_comment,
        json_deck_data_winner=json_deck_data_winner,
        json_deck_data_loser=json_deck_data_loser,
        winner_elo_change=winner_elo_change,
        loser_elo_change=loser_elo_change,
        winner_went_first=winner_went_first,
        loser_went_first=loser_went_first,
        winner_run_id=winner_run_id,
        loser_run_id=loser_run_id,
    )

    # Increment arena run records
    winner_run_complete = False
    loser_run_complete = False

    if winner_run_id:
        winner_run = get_arena_run(winner_run_id)
        if winner_run and winner_run["status"] == "active":
            update_arena_run_record(winner_run_id, winner_run["wins"] + 1, winner_run["losses"])
            winner_run_complete = check_run_complete(winner_run_id)

    if loser_run_id:
        loser_run = get_arena_run(loser_run_id)
        if loser_run and loser_run["status"] == "active":
            update_arena_run_record(loser_run_id, loser_run["wins"], loser_run["losses"] + 1)
            loser_run_complete = check_run_complete(loser_run_id)

    logger.info(
        "Limited match %d reported: winner=%s (run %s, complete=%s), loser=%s (run %s, complete=%s)",
        match_id, winner_id, winner_run_id, winner_run_complete,
        loser_id, loser_run_id, loser_run_complete,
    )

    return (match_id, winner_run_complete, loser_run_complete, winner_elo_change, loser_elo_change)


def limited_elo_only_report(
    reporter_id: int,
    winner_id: int,
    winner_display_name: str,
    loser_id: int,
    loser_display_name: str,
    first_player: str = "n",
    match_time: int = 0,
    curiosa_url_winner: str = "",
    curiosa_url_loser: str = "",
    match_comment: str = "",
    winner_went_first: str = "n",
    loser_went_first: str = "n",
    json_deck_data_winner: str = "{}",
    json_deck_data_loser: str = "{}",
) -> tuple:
    """Report a limited match that only affects ELO, not arena runs.

    Updates limited ELO for both players and inserts a match record,
    but does NOT increment wins/losses on any arena run.

    Returns:
        Tuple of (match_id, winner_new_elo, loser_new_elo)
    """
    event_active = bool(get_active_event())

    # Update Limited ELO for both players (skip between seasons)
    if event_active:
        winner_new_elo, winner_elo_change = update_limited_elo(winner_id, winner_display_name, True, loser_id)
        loser_new_elo, loser_elo_change = update_limited_elo(loser_id, loser_display_name, False, winner_id)
    else:
        logger.info("No active event — limited ELO-only match recorded without ELO changes")
        winner_new_elo = get_limited_elo(winner_id)
        loser_new_elo = get_limited_elo(loser_id)
        winner_elo_change = 0
        loser_elo_change = 0

    # Insert limited match record (no run IDs)
    match_id = insert_limited_match_record(
        reporter_id=reporter_id,
        winner_id=winner_id,
        winner_display_name=winner_display_name,
        loser_id=loser_id,
        loser_display_name=loser_display_name,
        did_win=True,
        first_player=first_player,
        match_time=match_time,
        curiosa_url_winner=curiosa_url_winner,
        curiosa_url_loser=curiosa_url_loser,
        match_comment=match_comment,
        json_deck_data_winner=json_deck_data_winner,
        json_deck_data_loser=json_deck_data_loser,
        winner_elo_change=winner_elo_change,
        loser_elo_change=loser_elo_change,
        winner_went_first=winner_went_first,
        loser_went_first=loser_went_first,
        winner_run_id=None,
        loser_run_id=None,
    )

    logger.info(
        "Limited ELO-only match %d reported: winner=%s (%d), loser=%s (%d)",
        match_id, winner_id, winner_new_elo, loser_id, loser_new_elo,
    )

    return (match_id, winner_new_elo, loser_new_elo)


def close_arena_run(user_id: int) -> str:
    """Close the active arena run without applying any ELO penalties.

    Used by admins to cleanly end a player's run.

    Returns:
        Run summary string after closing.
    """
    run = get_active_arena_run(user_id)
    if not run:
        raise ValueError(f"User {user_id} has no active arena run to close")

    run_id = run["run_id"]
    complete_arena_run(run_id, "closed")

    return get_run_summary(run_id)


def forfeit_arena_run(user_id: int) -> str:
    """Forfeit the active arena run, applying remaining losses as ELO penalty.

    Remaining losses are calculated as phantom losses against the starting ELO,
    applied sequentially.

    Returns:
        Run summary string after forfeit.
    """
    run = get_active_arena_run(user_id)
    if not run:
        raise ValueError(f"User {user_id} has no active arena run to forfeit")

    run_id = run["run_id"]
    losses_to_apply = MAX_ARENA_LOSSES - run["losses"]

    if losses_to_apply > 0:
        current_elo = get_limited_elo(user_id)
        original_elo = current_elo
        starting_elo = run["starting_elo"]

        for i in range(losses_to_apply):
            new_elo = update_elo(current_elo, starting_elo, did_win=False, k=32)
            logger.info(
                "Forfeit phantom loss %d/%d for user %s: %d -> %d (vs starting ELO %d)",
                i + 1, losses_to_apply, user_id, current_elo, new_elo, starting_elo,
            )
            current_elo = new_elo

        upsert_limited_elo(user_id, run["user_display_name"], current_elo, elo_change=current_elo - original_elo)

    # Update run record to show full loss cap and mark as forfeited
    update_arena_run_record(run_id, run["wins"], MAX_ARENA_LOSSES)
    complete_arena_run(run_id, "forfeited")

    return get_run_summary(run_id)


# --- Event Archive / Reset ---


def archive_limited_for_event(event_id: int, event_name: str) -> dict:
    """Archive all limited data at the end of an event.

    Copies standings, match records, and arena runs into their archive tables,
    then clears the live tables.

    Returns:
        dict with total_players, total_matches, total_runs, top_players (list of (name, elo))
    """
    import datetime as dt
    archived_at = dt.datetime.now().isoformat()

    # Close any active arena runs before archiving
    closed_runs = close_all_active_runs()
    if closed_runs:
        logger.info("Closed %d active arena runs before archiving event %d", closed_runs, event_id)

    standings = archive_limited_standings(event_id, event_name, archived_at)
    total_matches = archive_limited_matches(event_id, archived_at)
    total_runs = archive_limited_arena_runs(event_id, archived_at)

    top_3 = standings[:3]
    logger.info(
        "Limited event archive complete for event %d (%s): %d players, %d matches, %d runs",
        event_id, event_name, len(standings), total_matches, total_runs,
    )
    return {
        "total_players": len(standings),
        "total_matches": total_matches,
        "total_runs": total_runs,
        "top_players": [(name, elo) for _, name, elo in top_3],
    }


def reset_limited_for_new_event():
    """Reset limited ELO to 1500 for all players when a new event starts."""
    reset_limited_elo_to_default()
    logger.info("Limited ELO reset to 1500 for new event")
