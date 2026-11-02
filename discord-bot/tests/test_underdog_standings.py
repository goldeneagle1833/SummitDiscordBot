"""The underdog bracket standings card on the leaderboard message."""

from unittest.mock import AsyncMock, patch

import pytest

from services import underdog_standings as us


def standings():
    def avatar(name, score, player=None, excluded=False):
        return {"avatar": name, "avatar_score": score, "excluded": excluded, "player": player}

    players = [
        {"avatar": "Druid", "display_name": "Ann", "wins": 12, "losses": 4, "avatar_score": 700},
        {"avatar": "Witch", "display_name": "Bo_b", "wins": 9, "losses": 6, "avatar_score": 610},
    ]
    return {
        "success": True,
        "event": {"event_id": 8, "event_name": "Season 8"},
        "min_games": 10,
        "players": players,
        "avatars": [
            avatar("Frostmage", 300, excluded=True),
            avatar("Pathfinder", 320),
            avatar("Witch", 340, players[1]),
            avatar("Druid", 360, players[0]),
            avatar("Seer", 380),
            avatar("Sparkmage", 900),
        ],
    }


def test_card_lists_avatars_weakest_first_with_their_player():
    embed = us.build_embed(standings(), ["Frostmage"])
    lines = embed.description.split("\n")
    assert embed.title == us.CARD_TITLE
    assert lines[0] == "1. **Witch** (340) — Bo\\_b, 610 (9-6)"
    assert lines[1] == "2. **Druid** (360) — Ann, 700 (12-4)"
    assert "**Open:** Pathfinder" in embed.description
    assert "**Next up:** Seer, Sparkmage" in embed.description
    assert "**Left out:** Frostmage" in embed.description


def test_no_card_without_standings():
    assert us.build_embed(None) is None
    assert us.build_embed({"event": None}) is None


def test_left_out_matches_the_season_name_any_case():
    assert us.left_out_for(" season 8 ") == ["Frostmage", "Lavamancer"]
    assert us.left_out_for("Season 9") == []


@pytest.mark.asyncio
async def test_card_skipped_when_the_site_is_down():
    with patch.object(us, "fetch_standings", AsyncMock(return_value=None)) as fetch:
        assert await us.underdog_embed({"event_id": 8, "event_name": "Season 8"}) is None
    fetch.assert_awaited_once_with(8, ["Frostmage", "Lavamancer"])
    assert await us.underdog_embed(None) is None
