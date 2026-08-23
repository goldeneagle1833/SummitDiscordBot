import time
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg import state
from cogs.lfg.queue import match_delivery_extras, provision_match_and_publish_results
from cogs.lfg.queue_definitions import enabled_queue_definitions, queue_definition
from cogs.lfg.persistent_confirm import (
    create_match_card_view,
    ensure_match_cards_table,
    load_match_card_for_pairing,
)
from repositories.elo_repo import save_pairing
from services.matchmaking_api import _prune_results, _summit_member, start_matchmaking_api
from services.sorcery_online_matchmaking import (
    provision_sorcery_online_match,
    sorcery_online_matchmaking_enabled,
)
from services.summit_result_reporting import record_sorcery_online_result


def test_sorcery_online_matchmaking_is_opt_in(monkeypatch):
    monkeypatch.delenv("SORCERY_ONLINE_MATCHMAKING_ENABLED", raising=False)
    assert sorcery_online_matchmaking_enabled() is False

    for enabled_value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("SORCERY_ONLINE_MATCHMAKING_ENABLED", enabled_value)
        assert sorcery_online_matchmaking_enabled() is True

    for disabled_value in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("SORCERY_ONLINE_MATCHMAKING_ENABLED", disabled_value)
        assert sorcery_online_matchmaking_enabled() is False


def test_disabled_integration_adds_nothing_to_legacy_match_messages(monkeypatch):
    monkeypatch.delenv("SORCERY_ONLINE_MATCHMAKING_ENABLED", raising=False)
    extras = match_delivery_extras(
        {10: "https://example.test/seat/10", 20: "https://example.test/seat/20"},
        10,
        20,
    )
    assert extras == (None, None, "", "", "")


@pytest.mark.asyncio
async def test_disabled_integration_does_not_start_listener(monkeypatch):
    monkeypatch.delenv("SORCERY_ONLINE_MATCHMAKING_ENABLED", raising=False)
    with patch("services.matchmaking_api.web.AppRunner") as app_runner:
        runner = await start_matchmaking_api(MagicMock())
    assert runner is None
    app_runner.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_integration_never_calls_sorcery_online(monkeypatch):
    monkeypatch.delenv("SORCERY_ONLINE_MATCHMAKING_ENABLED", raising=False)
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "already-configured-key")
    with patch("services.sorcery_online_matchmaking.aiohttp.ClientSession") as session:
        links = await provision_sorcery_online_match(1, 2, "ranked", [])
    assert links is None
    session.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_integration_does_not_publish_website_results(monkeypatch):
    monkeypatch.delenv("SORCERY_ONLINE_MATCHMAKING_ENABLED", raising=False)
    state.matching_web_users.clear()
    state.pending_web_matches.clear()
    state.matching_web_users[10] = "ranked"
    players = [
        {
            "discord_user_id": 10,
            "display_name": "Web Player",
            "origin": "sorcery_online",
            "opponent_name": "Discord Player",
        },
        {
            "discord_user_id": 20,
            "display_name": "Discord Player",
            "origin": "discord",
            "opponent_name": "Web Player",
        },
    ]
    with patch(
        "cogs.lfg.queue.provision_sorcery_online_match",
        new=AsyncMock(),
    ) as provision:
        links = await provision_match_and_publish_results(1, 2, "ranked", players)
    assert links == {}
    provision.assert_not_awaited()
    assert state.pending_web_matches == {}
    assert state.matching_web_users == {}


@pytest.mark.asyncio
async def test_sorcery_online_result_is_idempotent_by_pairing(mock_bot):
    ensure_match_cards_table()
    pairing_id = save_pairing(1, 10, 20, "deck-a", "deck-b", "ranked")
    create_match_card_view(
        bot=mock_bot,
        pairing_id=pairing_id,
        player1_id=10,
        player1_global="Alice",
        player2_id=20,
        player2_global="Bob",
        guild_id=1,
        match_type="ranked",
    )

    async def record_once(_interaction, _confirmation_id, data, **_kwargs):
        from repositories.elo_repo import mark_pairing_reported
        mark_pairing_reported(1, data["winner_id"], data["loser_id"], pairing_id=pairing_id)
        return 77

    with patch(
        "services.summit_result_reporting._execute_match_confirmation",
        new=AsyncMock(side_effect=record_once),
    ) as execute:
        first = await record_sorcery_online_result(
            mock_bot,
            guild_id=1,
            pairing_id=pairing_id,
            queue_type="ranked",
            reporter_id=10,
            winner_id=10,
            loser_id=20,
        )
        retry = await record_sorcery_online_result(
            mock_bot,
            guild_id=1,
            pairing_id=pairing_id,
            queue_type="ranked",
            reporter_id=20,
            winner_id=10,
            loser_id=20,
        )
    assert first == {"recorded": True, "duplicate": False, "match_id": 77}
    assert retry == {"recorded": False, "duplicate": True, "match_id": None}
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_sorcery_online_result_rejects_queue_and_player_spoofing(mock_bot):
    pairing_id = save_pairing(1, 10, 20, "deck-a", "deck-b", "ranked")
    with pytest.raises(ValueError, match="Queue type"):
        await record_sorcery_online_result(
            mock_bot,
            guild_id=1,
            pairing_id=pairing_id,
            queue_type="testing",
            reporter_id=10,
            winner_id=10,
            loser_id=20,
        )
    with pytest.raises(ValueError, match="players"):
        await record_sorcery_online_result(
            mock_bot,
            guild_id=1,
            pairing_id=pairing_id,
            queue_type="ranked",
            reporter_id=10,
            winner_id=10,
            loser_id=30,
        )


def test_match_card_lookup_isolated_by_queue_type(mock_bot):
    ensure_match_cards_table()
    create_match_card_view(
        bot=mock_bot,
        pairing_id=5,
        player1_id=10,
        player1_global="Ranked Alice",
        player2_id=20,
        player2_global="Ranked Bob",
        guild_id=1,
        match_type="ranked",
    )
    create_match_card_view(
        bot=mock_bot,
        pairing_id=5,
        player1_id=30,
        player1_global="Limited Alice",
        player2_id=40,
        player2_global="Limited Bob",
        guild_id=1,
        match_type="limited",
    )
    assert load_match_card_for_pairing(5, "ranked")["player1_id"] == 10
    assert load_match_card_for_pairing(5, "limited")["player1_id"] == 30


def test_enabled_queue_definitions_are_pilot_driven():
    with patch("cogs.lfg.queue_definitions.is_pilot_active", side_effect=lambda pilot: pilot in {"RankedQueue", "GrewWolves"}):
        definitions = enabled_queue_definitions()
    assert [definition["type"] for definition in definitions] == ["ranked", "limited"]
    assert definitions[1]["deck_mode"] == "active_run"


def test_casual_metadata_preserves_existing_discord_emojis():
    definition = queue_definition("testing")
    assert definition["emoji"] == "⭐"
    assert definition["status_emoji"] == "🧪"


def test_pending_website_results_expire_after_delivery_window():
    state.pending_web_matches.clear()
    state.pending_web_matches[1] = {"id": "expired", "expires_at": time.time() - 1}
    state.pending_web_matches[2] = {"id": "active", "expires_at": time.time() + 60}
    _prune_results()
    assert 1 not in state.pending_web_matches
    assert state.pending_web_matches[2]["id"] == "active"


@pytest.mark.asyncio
async def test_missing_configured_guild_is_temporarily_unavailable():
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.get_guild.return_value = None
    with pytest.raises(web.HTTPServiceUnavailable):
        await _summit_member(bot, 123)
