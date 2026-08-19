from shared.avatar_qualification import build_avatar_top_cut


def _standing(user_id, avatar, elo):
    return {
        "user_id": str(user_id),
        "user_display_name": f"Player {user_id}",
        "avatar_name": avatar,
        "event_elo": elo,
    }


def _wins(user_id, avatar, count=3):
    return [
        {
            "winner_id": str(user_id),
            "winner_avatar": avatar,
            "loser_id": f"loser-{user_id}-{index}",
            "loser_avatar": "Other",
        }
        for index in range(count)
    ]


def test_avatar_leader_does_not_pass_to_second_place():
    standings = [
        _standing(1, "Impostor", 1700),
        _standing(2, "Impostor", 1690),
        _standing(3, "Battlemage", 1680),
    ]
    matches = _wins(2, "Impostor") + _wins(3, "Battlemage")
    result = build_avatar_top_cut(
        standings, matches, overall_seats=0, avatar_seats=8, total_seats=8
    )

    special = [
        seat for seat in result["seats"]
        if seat["qualification_path"] == "avatar_leader"
    ]
    assert [seat["player_id"] for seat in special] == ["3"]
    assert result["seats"][1]["player_id"] == "1"
    assert result["seats"][1]["qualification_path"] == "fallback"


def test_player_leading_multiple_avatars_gets_one_seat_without_inheritance():
    standings = [
        _standing(1, "Impostor", 1700),
        _standing(1, "Battlemage", 1690),
        _standing(2, "Battlemage", 1680),
    ]
    matches = _wins(1, "Impostor") + _wins(1, "Battlemage") + _wins(2, "Battlemage")
    result = build_avatar_top_cut(
        standings, matches, overall_seats=0, avatar_seats=8, total_seats=8
    )

    special = [
        seat for seat in result["seats"]
        if seat["qualification_path"] == "avatar_leader"
    ]
    assert len(special) == 1
    assert special[0]["player_id"] == "1"
    assert special[0]["qualifying_avatar"] == "Impostor"


def test_three_ranked_games_are_required_for_avatar_seat():
    result = build_avatar_top_cut(
        [_standing(1, "Impostor", 1700)],
        _wins(1, "Impostor", 2),
        overall_seats=0,
        avatar_seats=8,
        total_seats=8,
    )

    assert result["seats"][0]["qualification_path"] == "fallback"
    assert result["entries"][0]["qualification_reasons"] == [
        "needs_three_ranked_games"
    ]


def test_only_a_tie_crossing_the_seat_boundary_requires_tiebreak():
    standings = [
        _standing(1, "A", 1600),
        _standing(2, "B", 1600),
        _standing(3, "C", 1600),
    ]
    result = build_avatar_top_cut(
        standings,
        [],
        overall_seats=2,
        avatar_seats=0,
        total_seats=2,
    )

    assert all(seat["requires_tiebreak"] for seat in result["seats"])

    all_selected = build_avatar_top_cut(
        standings,
        [],
        overall_seats=3,
        avatar_seats=0,
        total_seats=3,
    )
    assert not any(seat["requires_tiebreak"] for seat in all_selected["seats"])
