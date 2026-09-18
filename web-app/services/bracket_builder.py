"""Single-elimination bracket maths.

Pure functions: entrants in, match tree out. No database, no Flask - so the
seeding and advancement rules can be tested on their own.
"""


def bracket_size_for(entrant_count: int) -> int:
    """Round an entrant count up to the next power of two.

    A 13-player field runs as a 16-slot bracket; the three empty slots become
    byes for the top seeds.
    """
    if entrant_count < 2:
        raise ValueError("A bracket needs at least 2 entrants")
    size = 2
    while size < entrant_count:
        size *= 2
    return size


def seed_order(bracket_size: int) -> list[int]:
    """Standard bracket seeding, flattened to first-round slot order.

    For 8 slots this gives [1, 8, 4, 5, 2, 7, 3, 6] - so seed 1 plays seed 8,
    and the top two seeds can only meet in the final.
    """
    if bracket_size < 2 or bracket_size & (bracket_size - 1):
        raise ValueError("Bracket size must be a power of two")

    order = [1, 2]
    while len(order) < bracket_size:
        size = len(order) * 2
        expanded = []
        for seed in order:
            expanded.append(seed)
            expanded.append(size + 1 - seed)
        order = expanded
    return order


def round_title(round_no: int, total_rounds: int) -> str:
    """Name a round the way players talk about it."""
    from_end = total_rounds - round_no
    if from_end == 0:
        return "Finals"
    if from_end == 1:
        return "Semifinals"
    if from_end == 2:
        return "Quarterfinals"
    return f"Round {round_no}"


def build_matches(entrants: list[dict]) -> list[dict]:
    """Generate the whole match tree for a seeded field.

    ``entrants`` is ordered by seed (seed 1 first). Slots past the entrant
    count are byes: the real player is advanced immediately, so a 13-player
    field opens with the top three seeds already sitting in round 2.
    """
    if len(entrants) < 2:
        raise ValueError("A bracket needs at least 2 entrants")

    size = bracket_size_for(len(entrants))
    total_rounds = size.bit_length() - 1
    by_seed = {index + 1: entrant for index, entrant in enumerate(entrants)}

    matches = []
    match_no = 0
    round_start = {}

    # Lay out every slot first so winners have somewhere to go.
    for round_no in range(1, total_rounds + 1):
        round_start[round_no] = match_no + 1
        for position in range(1, (size >> round_no) + 1):
            match_no += 1
            matches.append(
                {
                    "match_no": match_no,
                    "round": round_no,
                    "round_title": round_title(round_no, total_rounds),
                    "position": position,
                    "next_match_no": None,
                    "next_slot": None,
                    "p1_seed": None,
                    "p1_user_id": None,
                    "p1_name": None,
                    "p2_seed": None,
                    "p2_user_id": None,
                    "p2_name": None,
                    "winner_user_id": None,
                    "winner_seed": None,
                    "state": "pending",
                }
            )

    by_no = {m["match_no"]: m for m in matches}

    # Winner of match N in round r feeds slot 1 or 2 of the next round.
    for match in matches:
        if match["round"] == total_rounds:
            continue
        parent_position = (match["position"] + 1) // 2
        match["next_match_no"] = round_start[match["round"] + 1] + parent_position - 1
        match["next_slot"] = 1 if match["position"] % 2 else 2

    # Fill round one from the seeding order.
    order = seed_order(size)
    for index in range(0, size, 2):
        match = by_no[round_start[1] + index // 2]
        _place(match, 1, by_seed.get(order[index]), order[index])
        _place(match, 2, by_seed.get(order[index + 1]), order[index + 1])

    _resolve_byes(matches, by_no, total_rounds, round_start, size)
    return matches


def _resolve_byes(matches, by_no, total_rounds, round_start, size):
    """Walk the tree bottom-up, advancing anyone with nobody to play.

    An empty slot is only a bye when the branch feeding it holds no players at
    all. An empty slot waiting on a real match is just undecided, which is why
    this has to be worked out per round rather than per match.
    """
    # feeders[(match_no, slot)] = the match whose winner fills that slot
    feeders = {}
    for match in matches:
        if match["next_match_no"]:
            feeders[(match["next_match_no"], match["next_slot"])] = match

    empty = set()

    for round_no in range(1, total_rounds + 1):
        first = round_start[round_no]
        for position in range(1, (size >> round_no) + 1):
            match = by_no[first + position - 1]

            if round_no == 1:
                missing = {
                    slot for slot in (1, 2) if match[f"p{slot}_seed"] is None
                }
            else:
                missing = {
                    slot
                    for slot in (1, 2)
                    if match[f"p{slot}_seed"] is None
                    and feeders[(match["match_no"], slot)]["match_no"] in empty
                }

            if missing == {1, 2}:
                # Nothing below this slot at all - the whole branch is unused.
                empty.add(match["match_no"])
                match["state"] = "empty"
                continue

            if len(missing) == 1:
                present = 2 if 1 in missing else 1
                match["state"] = "bye"
                match["winner_seed"] = match[f"p{present}_seed"]
                match["winner_user_id"] = match[f"p{present}_user_id"]
                advance_winner(match, by_no)


def _place(match: dict, slot: int, entrant: dict | None, seed: int):
    """Put an entrant (or nothing, for a bye) into one side of a match."""
    if entrant is None:
        return
    match[f"p{slot}_seed"] = seed
    match[f"p{slot}_user_id"] = entrant.get("user_id")
    match[f"p{slot}_name"] = entrant.get("display_name")


def advance_winner(match: dict, by_no: dict) -> dict | None:
    """Move a decided match's winner into the next round. Returns that match."""
    if not match.get("next_match_no"):
        return None

    parent = by_no[match["next_match_no"]]
    slot = match["next_slot"]
    parent[f"p{slot}_seed"] = match["winner_seed"]
    parent[f"p{slot}_user_id"] = match["winner_user_id"]
    parent[f"p{slot}_name"] = winner_name(match)
    return parent


def winner_name(match: dict) -> str | None:
    """The display name of a decided match's winner."""
    if match.get("winner_seed") is None:
        return None
    if match["winner_seed"] == match["p1_seed"]:
        return match["p1_name"]
    return match["p2_name"]


def champion(matches: list[dict]) -> dict | None:
    """The winner of the last round, if the bracket has finished."""
    if not matches:
        return None
    final = max(matches, key=lambda m: (m["round"], m["position"]))
    if final.get("winner_seed") is None:
        return None
    return {
        "user_id": final.get("winner_user_id"),
        "seed": final.get("winner_seed"),
        "display_name": winner_name(final),
    }
