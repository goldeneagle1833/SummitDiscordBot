"""Business logic for the dust code reward system."""

import random
import re
import logging

from repositories.dust_repo import (
    add_dust_code,
    get_available_code_count,
    claim_next_code,
    has_player_claimed_this_season,
    increment_game_counter,
    record_drop,
    code_exists,
)
from repositories.audit_repo import log_admin_action

logger = logging.getLogger("discord_bot")

# Regex: 4 groups of 5 digits OR 5 groups of 4 digits separated by spaces
DUST_CODE_PATTERN_4x5 = re.compile(r"^\d{5} \d{5} \d{5} \d{5}$")
DUST_CODE_PATTERN_5x4 = re.compile(r"^\d{4} \d{4} \d{4} \d{4} \d{4}$")


def validate_dust_code(code_str):
    """Validate a dust code format. Returns True if valid."""
    stripped = code_str.strip()
    return bool(DUST_CODE_PATTERN_4x5.match(stripped) or DUST_CODE_PATTERN_5x4.match(stripped))


def donate_code(code_str, donor_id, donor_name):
    """Validate and store a donated dust code.

    Returns (success: bool, message: str).
    """
    code_str = code_str.strip()
    if not validate_dust_code(code_str):
        return False, "Invalid format. Codes must be 4 groups of 5 digits (`11111 22222 33333 44444`) or 5 groups of 4 digits (`1111 2222 3333 4444 5555`)"

    if code_exists(code_str):
        return False, "This code has already been loaded."

    add_dust_code(code_str, donor_id, donor_name)

    log_admin_action(
        admin_id=donor_id,
        admin_name=donor_name,
        action="dust_code_donated",
        details=f"{donor_name} donated a dust code",
    )

    remaining = get_available_code_count()
    return True, f"Dust code accepted! Thank you for your donation. ({remaining} codes available)"


def try_dust_drop(player1_id, player1_name, player2_id, player2_name, season_name):
    """Called after a match is confirmed. Rolls for a dust code drop.

    Returns (winner_id, winner_name, code) if a drop occurs, or None.
    """
    available = get_available_code_count()
    if available == 0:
        return None

    game_number, drop_chance, locked = increment_game_counter()

    # Already dropped a code this 100-game cycle
    if locked:
        logger.info(f"Dust drop skipped: game #{game_number}, cycle locked (already dropped)")
        return None

    # Roll for drop
    roll = random.random()
    logger.info(
        f"Dust drop roll: game #{game_number}, chance {drop_chance:.2%}, rolled {roll:.4f}"
    )
    if roll > drop_chance:
        return None

    # Drop triggered! Pick a random player
    p1_eligible = not has_player_claimed_this_season(player1_id, season_name)
    p2_eligible = not has_player_claimed_this_season(player2_id, season_name)

    if not p1_eligible and not p2_eligible:
        logger.info("Dust drop triggered but both players already claimed this season, skipping")
        return None

    # Pick winner
    if p1_eligible and p2_eligible:
        winner_id, winner_name = random.choice(
            [(player1_id, player1_name), (player2_id, player2_name)]
        )
    elif p1_eligible:
        winner_id, winner_name = player1_id, player1_name
    else:
        winner_id, winner_name = player2_id, player2_name

    # Claim the code
    code = claim_next_code(winner_id, winner_name, season_name)
    if code is None:
        logger.warning("Dust drop triggered but no codes available at claim time")
        return None

    record_drop(game_number)

    log_admin_action(
        admin_id=winner_id,
        admin_name=winner_name,
        action="dust_code_claimed",
        target_id=str(winner_id),
        target_name=winner_name,
        new_state={"season": season_name, "game_number": game_number},
        details=f"{winner_name} won a dust code drop (game #{game_number}, chance was {drop_chance:.2%})",
    )

    logger.info(f"Dust code dropped to {winner_name} (game #{game_number})")
    return winner_id, winner_name, code
