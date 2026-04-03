"""Business logic for Limited queue (arena draft mode).

Handles arena run management, limited ELO updates, and forfeit penalty calculation.
"""

import logging

from services.curiosa import CuriosaService
from repositories.limited_repo import (
    create_limited_tables,
    get_limited_elo,
    upsert_limited_elo,
    create_arena_run as _create_arena_run,
    get_active_arena_run,
    get_arena_run,
    update_arena_run_record,
    complete_arena_run,
)

logger = logging.getLogger(__name__)

create_limited_tables()


def _calculate_elo(player_elo, opponent_elo, did_win, k=32):
    """Calculate new ELO rating (standard ELO formula)."""
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0
    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)


def start_arena_run(user_id, display_name, deck_url):
    """Start a new arena run for a player.

    Raises ValueError if the user already has an active run.
    Returns dict with run info.
    """
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
    return get_arena_run(run_id)


def forfeit_arena_run(user_id):
    """Forfeit the active arena run, applying remaining losses as ELO penalty.

    Raises ValueError if no active run exists.
    Returns a summary string.
    """
    run = get_active_arena_run(user_id)
    if not run:
        raise ValueError(f"User {user_id} has no active arena run to forfeit")

    run_id = run["run_id"]
    losses_to_apply = 3 - run["losses"]

    if losses_to_apply > 0:
        current_elo = get_limited_elo(user_id)
        starting_elo = run["starting_elo"]

        for i in range(losses_to_apply):
            new_elo = _calculate_elo(current_elo, starting_elo, did_win=False, k=32)
            logger.info(
                "Forfeit phantom loss %d/%d for user %s: %d -> %d (vs starting ELO %d)",
                i + 1, losses_to_apply, user_id, current_elo, new_elo, starting_elo,
            )
            current_elo = new_elo

        upsert_limited_elo(user_id, run["user_display_name"], current_elo)

    update_arena_run_record(run_id, run["wins"], 3)
    complete_arena_run(run_id, "forfeited")

    # Build summary
    completed_run = get_arena_run(run_id)
    current_elo = get_limited_elo(user_id)
    elo_change = current_elo - run["starting_elo"]
    sign = "+" if elo_change >= 0 else ""

    return (
        f"Record: {completed_run['wins']}-{completed_run['losses']} | "
        f"Limited ELO: {current_elo} ({sign}{elo_change})"
    )
