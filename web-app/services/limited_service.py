"""Business logic for Limited queue (arena draft mode).

Handles arena run management, limited ELO updates, and forfeit penalty calculation.
"""

import logging

from services.curiosa import CuriosaService
from repositories.elo import EloRepository
from repositories.limited_repo import (
    create_limited_tables,
    get_limited_elo,
    upsert_limited_elo,
    create_arena_run as _create_arena_run,
    get_active_arena_run,
    get_arena_run,
    update_arena_run_record,
    complete_arena_run,
    insert_limited_match_record,
)

logger = logging.getLogger(__name__)

MAX_ARENA_WINS = 4
MAX_ARENA_LOSSES = 2

create_limited_tables()


def _calculate_elo(player_elo, opponent_elo, did_win, k=32):
    """Calculate new ELO rating (standard ELO formula)."""
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0
    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)


def start_arena_run(user_id, display_name, deck_url):
    """Start a new arena run for a player.

    Raises ValueError if the user already has an active run or no active event.
    Returns dict with run info.
    """
    if not EloRepository().get_active_event():
        raise ValueError("No active event — arena runs cannot be started between seasons.")

    active = get_active_arena_run(user_id)
    if active:
        raise ValueError(f"User {user_id} already has an active arena run (run_id={active['run_id']})")

    starting_elo = get_limited_elo(user_id)

    json_deck_data = "{}"
    try:
        if deck_url:
            json_deck_data = CuriosaService().fetch_deck_data(deck_url)
    except Exception as e:
        logger.warning("Failed to scrape deck data for arena run: %s", e)

    run_id = _create_arena_run(user_id, display_name, deck_url, json_deck_data, starting_elo)
    run = get_arena_run(run_id)
    if run is None:
        raise RuntimeError(f"Failed to load arena run {run_id} after creation")
    return run


def _check_run_complete(run_id):
    """Check if an arena run has reached completion (4W or 2L). Auto-completes if so."""
    run = get_arena_run(run_id)
    if not run or run["status"] != "active":
        return run is not None and run["status"] != "active"

    if run["wins"] >= MAX_ARENA_WINS or run["losses"] >= MAX_ARENA_LOSSES:
        complete_arena_run(run_id, "completed")
        logger.info("Arena run %d completed: %d-%d", run_id, run["wins"], run["losses"])
        return True
    return False


def report_match(winner_id, winner_display_name, loser_id, loser_display_name,
                 first_player=None, match_time=None, match_comment=None):
    """Report a limited match result from a 3rd party source.

    Both players must have active arena runs. Updates limited ELO for both,
    inserts a match record, increments run win/loss counts, and auto-completes
    runs that hit thresholds (4W or 2L).

    Returns dict with match_id, ELO changes, and run statuses.
    Raises ValueError if either player lacks an active run.
    ELO is only updated when an active event exists (skipped between seasons).
    """
    event_active = bool(EloRepository().get_active_event())

    winner_run = get_active_arena_run(winner_id)
    loser_run = get_active_arena_run(loser_id)

    if not winner_run:
        raise ValueError(f"Winner {winner_id} has no active arena run")
    if not loser_run:
        raise ValueError(f"Loser {loser_id} has no active arena run")

    winner_run_id = winner_run["run_id"]
    loser_run_id = loser_run["run_id"]

    # Update limited ELO for both players (skip between seasons)
    winner_elo_before = get_limited_elo(winner_id)
    loser_elo_before = get_limited_elo(loser_id)

    if event_active:
        new_winner_elo = _calculate_elo(winner_elo_before, loser_elo_before, did_win=True)
        new_loser_elo = _calculate_elo(loser_elo_before, winner_elo_before, did_win=False)

        winner_elo_change = new_winner_elo - winner_elo_before
        loser_elo_change = new_loser_elo - loser_elo_before

        upsert_limited_elo(winner_id, winner_display_name, new_winner_elo, elo_change=winner_elo_change)
        upsert_limited_elo(loser_id, loser_display_name, new_loser_elo, elo_change=loser_elo_change)
    else:
        logger.info("No active event — limited match recorded without ELO changes")
        new_winner_elo = winner_elo_before
        new_loser_elo = loser_elo_before
        winner_elo_change = 0
        loser_elo_change = 0

    # Determine who went first
    winner_went_first = "y" if first_player == str(winner_id) else "n"
    loser_went_first = "y" if first_player == str(loser_id) else "n"

    # Insert match record
    match_id = insert_limited_match_record(
        reporter_id=0,  # API-reported
        winner_id=winner_id,
        winner_display_name=winner_display_name,
        loser_id=loser_id,
        loser_display_name=loser_display_name,
        did_win=True,
        first_player=first_player or "",
        match_time=match_time or 0,
        curiosa_url_winner=winner_run["deck_url"],
        curiosa_url_loser=loser_run["deck_url"],
        match_comment=match_comment or "",
        json_deck_data_winner=winner_run.get("json_deck_data", "{}"),
        json_deck_data_loser=loser_run.get("json_deck_data", "{}"),
        winner_elo_change=winner_elo_change,
        loser_elo_change=loser_elo_change,
        winner_went_first=winner_went_first,
        loser_went_first=loser_went_first,
        winner_run_id=winner_run_id,
        loser_run_id=loser_run_id,
    )

    # Update arena run records
    update_arena_run_record(winner_run_id, winner_run["wins"] + 1, winner_run["losses"])
    update_arena_run_record(loser_run_id, loser_run["wins"], loser_run["losses"] + 1)

    # Check if either run is now complete
    winner_run_complete = _check_run_complete(winner_run_id)
    loser_run_complete = _check_run_complete(loser_run_id)

    logger.info(
        "API match %d reported: winner=%s (%+d), loser=%s (%+d)",
        match_id, winner_id, winner_elo_change, loser_id, loser_elo_change,
    )

    return {
        "match_id": match_id,
        "winner": {
            "user_id": winner_id,
            "display_name": winner_display_name,
            "elo": new_winner_elo,
            "elo_change": winner_elo_change,
            "run_id": winner_run_id,
            "run_wins": winner_run["wins"] + 1,
            "run_losses": winner_run["losses"],
            "run_complete": winner_run_complete,
        },
        "loser": {
            "user_id": loser_id,
            "display_name": loser_display_name,
            "elo": new_loser_elo,
            "elo_change": loser_elo_change,
            "run_id": loser_run_id,
            "run_wins": loser_run["wins"],
            "run_losses": loser_run["losses"] + 1,
            "run_complete": loser_run_complete,
        },
    }


def close_arena_run(user_id):
    """Close the active arena run without applying any ELO penalties.

    Used by admins to cleanly end a player's run.
    Raises ValueError if no active run exists.
    Returns a summary string.
    """
    run = get_active_arena_run(user_id)
    if not run:
        raise ValueError(f"User {user_id} has no active arena run to close")

    run_id = run["run_id"]
    complete_arena_run(run_id, "closed")

    completed_run = get_arena_run(run_id)
    if completed_run is None:
        raise RuntimeError(f"Failed to load arena run {run_id} after close")
    current_elo = get_limited_elo(user_id)
    elo_change = current_elo - run["starting_elo"]
    sign = "+" if elo_change >= 0 else ""

    return (
        f"Record: {completed_run['wins']}-{completed_run['losses']} | "
        f"Limited ELO: {current_elo} ({sign}{elo_change})"
    )


def forfeit_arena_run(user_id):
    """Forfeit the active arena run, applying remaining losses as ELO penalty.

    Raises ValueError if no active run exists.
    Returns a summary string.
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
            new_elo = _calculate_elo(current_elo, starting_elo, did_win=False, k=32)
            logger.info(
                "Forfeit phantom loss %d/%d for user %s: %d -> %d (vs starting ELO %d)",
                i + 1, losses_to_apply, user_id, current_elo, new_elo, starting_elo,
            )
            current_elo = new_elo

        upsert_limited_elo(user_id, run["user_display_name"], current_elo, elo_change=current_elo - original_elo)

    update_arena_run_record(run_id, run["wins"], MAX_ARENA_LOSSES)
    complete_arena_run(run_id, "forfeited")

    # Build summary
    completed_run = get_arena_run(run_id)
    if completed_run is None:
        raise RuntimeError(f"Failed to load arena run {run_id} after forfeit")
    current_elo = get_limited_elo(user_id)
    elo_change = current_elo - run["starting_elo"]
    sign = "+" if elo_change >= 0 else ""

    return (
        f"Record: {completed_run['wins']}-{completed_run['losses']} | "
        f"Limited ELO: {current_elo} ({sign}{elo_change})"
    )
