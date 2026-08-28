import json
import sqlite3
import time
import sys
from pathlib import Path
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
from repositories.elo_repo import get_pairing_by_id, save_pairing
from services.matchmaking_api import (
    _authentication,
    _is_loopback_request,
    _prune_results,
    _summit_member,
    start_matchmaking_api,
)
from services import sorcery_online_matchmaking
from services.sorcery_online_matchmaking import (
    provision_sorcery_online_match,
    summit_matchmaking_api_key,
)
from services.summit_result_reporting import record_sorcery_online_result


def test_missing_links_add_nothing_to_legacy_match_messages():
    assert match_delivery_extras({}, 10, 20) == (None, None, "", "", "")
    assert match_delivery_extras(
        {10: "https://example.test/seat/10"},
        10,
        20,
    ) == (None, None, "", "", "")


def test_complete_links_add_private_seats_and_voice_reminder():
    reporter_url = "https://example.test/seat/10"
    other_url = "https://example.test/seat/20"
    extras = match_delivery_extras({10: reporter_url, 20: other_url}, 10, 20)
    assert extras[0] == reporter_url
    assert extras[1] == other_url
    assert reporter_url in extras[2]
    assert other_url in extras[3]
    assert "Join To Make a Room" in extras[4]


def test_matchmaking_key_prefers_shared_bot_env(monkeypatch, tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("DRAFT_SORCERY_API_KEY=shared-file-key\n", encoding="utf-8")
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "stale-process-key")
    monkeypatch.setattr(sorcery_online_matchmaking, "BOT_ENV_PATH", env_path)
    assert summit_matchmaking_api_key() == "shared-file-key"


def test_bot_api_accepts_only_loopback_callers():
    assert _is_loopback_request(MagicMock(remote="127.0.0.1")) is True
    assert _is_loopback_request(MagicMock(remote="::1")) is True
    assert _is_loopback_request(MagicMock(remote="203.0.113.10")) is False


@pytest.mark.asyncio
async def test_bot_api_rejects_non_loopback_callers():
    with pytest.raises(web.HTTPForbidden) as exc_info:
        await _authentication(MagicMock(remote="203.0.113.10"), AsyncMock())
    assert exc_info.value.text == "Loopback access only"


@pytest.mark.asyncio
async def test_matchmaking_listener_starts_without_feature_flag():
    runner = MagicMock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = MagicMock()
    site.start = AsyncMock()
    with (
        patch("services.matchmaking_api.web.AppRunner", return_value=runner),
        patch("services.matchmaking_api.web.TCPSite", return_value=site),
    ):
        result = await start_matchmaking_api(MagicMock())
    assert result is runner
    runner.setup.assert_awaited_once()
    site.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_matchmaking_listener_failure_does_not_stop_the_bot():
    runner = MagicMock()
    runner.setup = AsyncMock(side_effect=OSError("port already in use"))
    runner.cleanup = AsyncMock()
    with patch("services.matchmaking_api.web.AppRunner", return_value=runner):
        result = await start_matchmaking_api(MagicMock())
    assert result is None
    runner.cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_key_skips_sorcery_online_provisioning(monkeypatch):
    monkeypatch.delenv("DRAFT_SORCERY_API_KEY", raising=False)
    with patch("services.sorcery_online_matchmaking.aiohttp.ClientSession") as session:
        links = await provision_sorcery_online_match(1, 2, "ranked", [])
    assert links is None
    session.assert_not_called()


@pytest.mark.asyncio
async def test_unavailable_sorcery_online_provisioning_is_non_fatal(monkeypatch):
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "configured-key")
    with patch(
        "services.sorcery_online_matchmaking.aiohttp.ClientSession",
        side_effect=OSError("endpoint unavailable"),
    ):
        links = await provision_sorcery_online_match(1, 2, "ranked", [])
    assert links is None


@pytest.mark.asyncio
async def test_unavailable_provisioning_still_publishes_website_results():
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
        new=AsyncMock(return_value=None),
    ) as provision:
        links = await provision_match_and_publish_results(1, 2, "ranked", players)
    assert links == {}
    provision.assert_awaited_once()
    assert state.pending_web_matches[10]["game_url"] is None
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
async def test_unknown_sorcery_online_outcome_leaves_pairing_active(mock_bot):
    """Unknown outcomes leave the pairing active so players can report via Discord."""
    pairing_id = save_pairing(1, 10, 20, "deck-a", "deck-b", "ranked")
    players = [
        {
            "player_id": "10",
            "played_cards": [
                {"card_id": "site-a", "card_name": "Site A", "quantity": 2},
            ],
        },
        {"player_id": "20", "played_cards": []},
    ]
    result = await record_sorcery_online_result(
        mock_bot,
        guild_id=1,
        pairing_id=pairing_id,
        queue_type="ranked",
        outcome="unknown",
        reporter_id=None,
        winner_id=None,
        loser_id=None,
        players=players,
    )
    assert result == {
        "recorded": False,
        "duplicate": False,
        "match_id": None,
        "outcome": "unknown",
    }
    # Unknown should NOT close the pairing — it stays active
    assert get_pairing_by_id(1, pairing_id)["status"] == "active"


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


# ── Sorcery Online results: payload casing, audit table robustness ──

from services.matchmaking_api import _result_fields
from services import summit_result_reporting


def test_result_fields_accept_snake_and_camel_case():
    snake = _result_fields({
        "queue_type": "ranked", "reporter_id": "20",
        "winner_id": "10", "loser_id": "20", "players": [],
    })
    camel = _result_fields({
        "queueType": "ranked", "reporterId": "20",
        "winnerId": "10", "loserId": "20", "playedCards": [],
    })
    assert snake == camel
    assert snake["queue_type"] == "ranked"
    assert snake["outcome"] == "decided"
    assert snake["reporter_id"] == "20"


def test_result_fields_default_reporter_to_winner_for_decided():
    fields = _result_fields({"queueType": "ranked", "winnerId": 10, "loserId": 20})
    assert fields["reporter_id"] == 10


def test_result_fields_do_not_invent_reporter_for_non_decided():
    fields = _result_fields({"queue_type": "ranked", "outcome": "UNKNOWN"})
    assert fields["outcome"] == "unknown"
    assert fields["reporter_id"] is None


@pytest.mark.asyncio
async def test_camel_case_result_payload_records_match(mock_bot):
    ensure_match_cards_table()
    pairing_id = save_pairing(1, 10, 20, "deck-a", "deck-b", "ranked")

    async def record_once(_interaction, _confirmation_id, data, **_kwargs):
        from repositories.elo_repo import mark_pairing_reported
        mark_pairing_reported(1, data["winner_id"], data["loser_id"], pairing_id=pairing_id)
        return 91

    with patch(
        "services.summit_result_reporting._execute_match_confirmation",
        new=AsyncMock(side_effect=record_once),
    ):
        result = await record_sorcery_online_result(
            mock_bot,
            guild_id=1,
            pairing_id=pairing_id,
            **_result_fields({"queueType": "ranked", "winnerId": "10", "loserId": "20"}),
        )
    assert result == {"recorded": True, "duplicate": False, "match_id": 91}
    assert get_pairing_by_id(1, pairing_id)["status"] == "reported"


def test_callback_table_migrates_legacy_schema():
    conn = sqlite3.connect("match_records.db")
    conn.execute("""CREATE TABLE sorcery_online_match_callbacks (
        guild_id INTEGER NOT NULL, pairing_id INTEGER NOT NULL,
        queue_type TEXT NOT NULL, outcome TEXT NOT NULL,
        reporter_id INTEGER, winner_id INTEGER, loser_id INTEGER,
        played_cards_json TEXT NOT NULL, match_id INTEGER, received_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, pairing_id, queue_type))""")
    conn.execute(
        "INSERT INTO sorcery_online_match_callbacks VALUES (1, 5, 'ranked', 'decided', 10, 10, 20, '[]', 3, 'x')"
    )
    conn.commit()
    conn.close()

    summit_result_reporting._save_callback(1, 6, "ranked", "decided", 10, 10, 20, 4, None, None)

    conn = sqlite3.connect("match_records.db")
    new_rows = conn.execute(
        "SELECT pairing_id, match_id FROM sorcery_online_match_callbacks"
    ).fetchall()
    legacy_rows = conn.execute(
        "SELECT pairing_id, match_id FROM sorcery_online_match_callbacks_legacy"
    ).fetchall()
    conn.close()
    assert new_rows == [(6, 4)]
    assert legacy_rows == [(5, 3)]


def test_callback_save_failure_is_not_fatal(monkeypatch):
    def boom(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(summit_result_reporting, "_ensure_callback_table", boom)
    # Must not raise: audit rows are bookkeeping, never a reason to fail a result
    summit_result_reporting._save_callback(1, 6, "ranked", "decided", 10, 10, 20, 4, None, None)
