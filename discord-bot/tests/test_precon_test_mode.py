"""PSO test mode for the precon queue: 200s with sample data, nothing queued or recorded."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from services import precon_service, precon_test_mode  # noqa: E402
from services.matchmaking_api import start_matchmaking_api  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_cache():
    precon_service.clear_cache()
    yield
    precon_service.clear_cache()


async def _handler(path, method):
    runner = MagicMock(setup=AsyncMock(), cleanup=AsyncMock())
    site = MagicMock(start=AsyncMock())
    with (
        patch("services.matchmaking_api.web.AppRunner", return_value=runner) as app_runner,
        patch("services.matchmaking_api.web.TCPSite", return_value=site),
    ):
        await start_matchmaking_api(MagicMock())
    app = app_runner.call_args[0][0]
    for route in app.router.routes():
        if route.resource.canonical == path and route.method == method:
            return route.handler
    raise AssertionError(path)


def _request(payload, **match_info):
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    request.match_info = match_info
    return request


RESULT = {
    "queue_type": "precon", "winner_id": "111", "loser_id": "222",
    "replay_url": "https://example.test/replay/1",
    "players": [{"discordUserId": "111", "precon": "LM"}, {"discordUserId": "222", "precon": "frostmage"}],
}


def test_test_mode_is_off_by_default_and_never_beats_a_live_queue():
    assert precon_service.test_mode_active() is False
    precon_service.update_settings({"pso_test_mode": True})
    assert precon_service.test_mode_active() is True
    precon_service.start_season("Live one")
    precon_service.update_settings({"queue_enabled": True})
    assert precon_service.test_mode_active() is False  # the real queue answers instead


def test_join_needs_no_pick_and_returns_a_random_sample_table_request():
    body = precon_test_mode.test_join({}, 111, "Alice", "voice")
    assert body["test_mode"] is True and body["accepted"]["precon_assignment"] == "random"
    players = body["sample_table_request"]["players"]
    assert players[0]["discordUserId"] == "111" and players[0]["deckUrl"] is None
    assert sorted(p["precon"] for p in players) == ["frostmage", "lavamancer"]


def test_status_entry_is_marked_as_test():
    entry = precon_test_mode.test_queue_entry(["voice", "no_voice"], "voice")
    assert entry["type"] == "precon" and entry["test_mode"] is True
    assert [c["key"] for c in entry["precon_choices"]] == ["lavamancer", "frostmage"]


@pytest.mark.asyncio
async def test_result_in_test_mode_is_echoed_not_recorded():
    precon_service.update_settings({"pso_test_mode": True})
    handler = await _handler("/matches/{guild_id}/{pairing_id}/results", "POST")
    with patch("services.matchmaking_api.record_sorcery_online_result", new=AsyncMock()) as record:
        response = await handler(_request(RESULT, guild_id="1", pairing_id="999999"))
        record.assert_not_called()
    assert response.status == 200
    body = json.loads(response.body)
    assert body["recorded"] is False
    assert body["would_record"]["winner_precon"] == "lavamancer"
    assert body["would_record"]["loser_precon"] == "frostmage"
    assert body["would_record"]["replay_url"] == "https://example.test/replay/1"
    bad = await handler(_request({**RESULT, "loser_id": "111"}, guild_id="1", pairing_id="test"))
    assert bad.status == 400


@pytest.mark.asyncio
async def test_result_without_test_mode_still_needs_a_real_pairing():
    handler = await _handler("/matches/{guild_id}/{pairing_id}/results", "POST")
    with patch(
        "services.matchmaking_api.record_sorcery_online_result",
        new=AsyncMock(side_effect=LookupError("Pairing not found")),
    ):
        response = await handler(_request(RESULT, guild_id="1", pairing_id="999999"))
    assert response.status == 404
