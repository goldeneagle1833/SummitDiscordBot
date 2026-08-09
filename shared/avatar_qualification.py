"""Pure qualification rules for an avatar-specific Elo event.

The database and Discord-role adapters live in each application. Keeping the
policy here prevents the bot, website, archives, and admin previews from
silently applying different top-cut rules.
"""

from collections.abc import Iterable


def summarize_avatar_records(matches: Iterable[dict]) -> dict[tuple[str, str], dict]:
    """Return ranked-game wins/losses for each player/avatar combination."""
    records: dict[tuple[str, str], dict] = {}

    def add(user_id, avatar, *, won: bool) -> None:
        if user_id is None or not avatar:
            return
        key = (str(user_id), str(avatar).casefold())
        record = records.setdefault(key, {"games": 0, "wins": 0, "losses": 0})
        record["games"] += 1
        record["wins" if won else "losses"] += 1

    for match in matches:
        add(match.get("winner_id"), match.get("winner_avatar"), won=True)
        add(match.get("loser_id"), match.get("loser_avatar"), won=False)

    for record in records.values():
        record["win_rate"] = (
            record["wins"] / record["games"] if record["games"] else 0.0
        )
    return records


def build_avatar_top_cut(
    standings: Iterable[dict],
    matches: Iterable[dict],
    *,
    eligible_user_ids: Iterable[str | int] | None = None,
    overall_seats: int = 16,
    avatar_seats: int = 8,
    total_seats: int = 24,
    minimum_avatar_games: int = 3,
) -> dict:
    """Build unique-player qualification seats for the proposed 16+8 format."""
    eligible = (
        None
        if eligible_user_ids is None
        else {str(user_id) for user_id in eligible_user_ids}
    )
    records = summarize_avatar_records(matches)
    entries = []
    for standing in standings:
        user_id = str(standing["user_id"])
        avatar_name = str(standing["avatar_name"])
        record = records.get(
            (user_id, avatar_name.casefold()),
            {"games": 0, "wins": 0, "losses": 0, "win_rate": 0.0},
        )
        entries.append(
            {
                **standing,
                "user_id": user_id,
                "avatar_name": avatar_name,
                "event_elo": int(standing["event_elo"]),
                **record,
            }
        )

    def entry_key(entry: dict) -> tuple:
        # Display names are never competitive tiebreakers. Exact remaining ties
        # are surfaced to admins through `requires_tiebreak`.
        return (
            -entry["event_elo"],
            -entry["wins"],
            -entry["win_rate"],
            -entry["games"],
            entry["user_id"],
            entry["avatar_name"].casefold(),
        )

    def competitive_key(entry: dict) -> tuple:
        return (
            entry["event_elo"],
            entry["wins"],
            entry["win_rate"],
            entry["games"],
        )

    entries.sort(key=entry_key)
    for index, entry in enumerate(entries, 1):
        entry["overall_entry_rank"] = index
        entry["eligible_player"] = eligible is None or entry["user_id"] in eligible

    seats = []
    qualified = set()

    def add_seat(entry: dict, path: str) -> None:
        qualified.add(entry["user_id"])
        seats.append(
            {
                "seat": len(seats) + 1,
                "player_id": entry["user_id"],
                "player_name": entry["user_display_name"],
                "qualifying_avatar": entry["avatar_name"],
                "qualifying_elo": entry["event_elo"],
                "qualification_path": path,
                "overall_entry_rank": entry["overall_entry_rank"],
                "games": entry["games"],
                "wins": entry["wins"],
                "losses": entry["losses"],
                "win_rate": entry["win_rate"],
                "requires_tiebreak": False,
            }
        )

    def best_unique_candidates(pool: Iterable[dict]) -> list[dict]:
        candidates = []
        seen_players = set(qualified)
        for entry in pool:
            if not entry["eligible_player"] or entry["user_id"] in seen_players:
                continue
            seen_players.add(entry["user_id"])
            candidates.append(entry)
        return candidates

    stage_boundaries = []
    overall_candidates = best_unique_candidates(entries)
    overall_selected = overall_candidates[:overall_seats]
    for entry in overall_selected:
        add_seat(entry, "overall")
    stage_boundaries.append(("overall", overall_candidates, len(overall_selected)))

    avatar_groups: dict[str, list[dict]] = {}
    for entry in entries:
        avatar_groups.setdefault(entry["avatar_name"].casefold(), []).append(entry)

    absolute_leaders = []
    for avatar_entries in avatar_groups.values():
        avatar_entries.sort(key=entry_key)
        leader = avatar_entries[0]
        leader["absolute_avatar_rank"] = 1
        leader["avatar_seat_eligible"] = (
            leader["eligible_player"]
            and leader["user_id"] not in qualified
            and leader["games"] >= minimum_avatar_games
            and leader["wins"] > leader["losses"]
        )
        absolute_leaders.append(leader)

    # A player leading several avatars gets one special seat using their highest
    # eligible entry. The other avatar never passes down to its #2 player.
    best_leader_by_player = {}
    for leader in absolute_leaders:
        if not leader["avatar_seat_eligible"]:
            continue
        current = best_leader_by_player.get(leader["user_id"])
        if current is None or entry_key(leader) < entry_key(current):
            best_leader_by_player[leader["user_id"]] = leader

    special_candidates = sorted(best_leader_by_player.values(), key=entry_key)
    special_selected = special_candidates[:avatar_seats]
    for candidate in special_selected:
        add_seat(candidate, "avatar_leader")
    stage_boundaries.append(
        ("avatar_leader", special_candidates, len(special_selected))
    )

    fallback_candidates = best_unique_candidates(entries)
    fallback_selected = fallback_candidates[:max(0, total_seats - len(seats))]
    for entry in fallback_selected:
        add_seat(entry, "fallback")
    stage_boundaries.append(
        ("fallback", fallback_candidates, len(fallback_selected))
    )

    # Only flag a tie when it crosses an actual seat boundary. Ties among
    # players who all made the cut do not require an admin decision.
    for path, candidates, selected_count in stage_boundaries:
        if selected_count == 0 or selected_count >= len(candidates):
            continue
        boundary_key = competitive_key(candidates[selected_count - 1])
        if competitive_key(candidates[selected_count]) != boundary_key:
            continue
        for seat in seats:
            if (
                seat["qualification_path"] == path
                and (
                    seat["qualifying_elo"],
                    seat["wins"],
                    seat["win_rate"],
                    seat["games"],
                ) == boundary_key
            ):
                seat["requires_tiebreak"] = True

    seat_by_player = {seat["player_id"]: seat for seat in seats}
    entry_status = []
    leader_ids = {
        (leader["user_id"], leader["avatar_name"].casefold())
        for leader in absolute_leaders
    }
    for entry in entries:
        seat = seat_by_player.get(entry["user_id"])
        entry_is_qualifying = bool(
            seat
            and seat["qualifying_avatar"].casefold()
            == entry["avatar_name"].casefold()
        )
        is_absolute_leader = (
            entry["user_id"], entry["avatar_name"].casefold()
        ) in leader_ids
        reasons = []
        if is_absolute_leader:
            if not entry["eligible_player"]:
                reasons.append("player_not_top_cut_eligible")
            if entry["games"] < minimum_avatar_games:
                reasons.append("needs_three_ranked_games")
            if entry["wins"] <= entry["losses"]:
                reasons.append("needs_positive_win_rate")
            if seat and seat["qualification_path"] == "overall":
                reasons.append("already_qualified_overall")
        entry_status.append(
            {
                **entry,
                "absolute_avatar_leader": is_absolute_leader,
                "qualified": entry_is_qualifying,
                "player_qualified": seat is not None,
                "qualification_path": (
                    seat["qualification_path"] if entry_is_qualifying else None
                ),
                "qualification_reasons": reasons,
            }
        )

    return {
        "seats": seats,
        "entries": entry_status,
        "policy": {
            "overall_seats": overall_seats,
            "avatar_seats": avatar_seats,
            "total_seats": total_seats,
            "minimum_avatar_games": minimum_avatar_games,
            "positive_win_rate_required": True,
            "avatar_leader_inheritance": False,
        },
    }
