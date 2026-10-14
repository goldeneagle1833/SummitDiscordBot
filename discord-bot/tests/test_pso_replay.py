"""Sorcery Online replay links: saved from the table, carried onto the match."""

import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg.queue import provision_match_and_publish_results
from repositories.elo_repo import (
    clean_replay_url,
    get_pairing_replay,
    save_pairing,
    set_pairing_replay,
)
from services.elo_service import record_match
from services.sorcery_online_matchmaking import provision_sorcery_online_match

REPLAY = "https://playsorceryonline.com/replay/lZCHVAbWU8UyASz5LkW9iXhtf47Bdt7G"


def _stored_replay(match_id):
    conn = sqlite3.connect("match_records.db")
    try:
        return conn.execute(
            "SELECT replay_url FROM match_records WHERE match_id = ?", (match_id,)
        ).fetchone()[0]
    finally:
        conn.close()


async def _record(pairing_id=None):
    with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
         patch("services.elo_service.get_active_event", return_value=None):
        result = await record_match(10, 10, "A", 20, "B", "y", 20, "", None, None,
                                    "y", "n", pairing_id=pairing_id)
    return result[0]


def test_only_sorcery_online_links_are_kept():
    assert clean_replay_url(REPLAY) == REPLAY
    assert clean_replay_url("https://www.playsorceryonline.com/replays/x") is not None
    assert clean_replay_url("https://evil.example/replay/x") is None
    assert clean_replay_url("javascript:alert(1)") is None
    assert clean_replay_url("") is None
    assert clean_replay_url(None) is None


@pytest.mark.asyncio
async def test_record_match_copies_replay_from_pairing():
    pairing_id = save_pairing(1, 10, 20, "", "", "ranked")
    assert set_pairing_replay(pairing_id, REPLAY) is True
    assert get_pairing_replay(pairing_id) == REPLAY

    with_replay = await _record(pairing_id)
    without = await _record()
    assert _stored_replay(with_replay) == REPLAY
    assert _stored_replay(without) is None


@pytest.mark.asyncio
async def test_replay_arriving_after_the_result_fills_in_the_match():
    pairing_id = save_pairing(1, 10, 20, "", "", "ranked")
    match_id = await _record(pairing_id)
    assert _stored_replay(match_id) is None

    set_pairing_replay(pairing_id, REPLAY)
    assert _stored_replay(match_id) == REPLAY


def test_non_sorcery_online_link_is_ignored():
    pairing_id = save_pairing(1, 10, 20, "", "", "ranked")
    assert set_pairing_replay(pairing_id, "https://evil.example/replay") is False
    assert get_pairing_replay(pairing_id) is None


def _table_session(body):
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value=body)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.post.return_value = response
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


SEATS = [
    {"discordUserId": "10", "gameUrl": "https://playsorceryonline.com/?m=one"},
    {"discordUserId": "20", "gameUrl": "https://playsorceryonline.com/?m=two"},
]


@pytest.mark.asyncio
async def test_table_replay_link_is_handed_back(monkeypatch):
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "configured-key")
    seen = []
    session = _table_session({"players": SEATS, "replayUrl": REPLAY})
    with patch("services.sorcery_online_matchmaking.aiohttp.ClientSession", return_value=session):
        links = await provision_sorcery_online_match(
            1, 2, "ranked", [], on_replay_url=seen.append,
        )
    assert links == {10: SEATS[0]["gameUrl"], 20: SEATS[1]["gameUrl"]}
    assert seen == [REPLAY]


@pytest.mark.asyncio
async def test_queue_pairing_saves_the_table_replay(monkeypatch):
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "configured-key")
    pairing_id = save_pairing(1, 10, 20, "", "", "ranked")
    players = [
        {"discord_user_id": 10, "display_name": "A", "origin": "discord", "opponent_name": "B"},
        {"discord_user_id": 20, "display_name": "B", "origin": "discord", "opponent_name": "A"},
    ]
    session = _table_session({"players": SEATS, "replayUrl": REPLAY})
    with patch("services.sorcery_online_matchmaking.aiohttp.ClientSession", return_value=session):
        await provision_match_and_publish_results(1, pairing_id, "ranked", players)
    assert get_pairing_replay(pairing_id) == REPLAY


@pytest.mark.asyncio
async def test_limited_pairing_never_saves_a_replay(monkeypatch):
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "configured-key")
    # A limited pairing id can collide with a queue pairing id
    pairing_id = save_pairing(1, 10, 20, "", "", "ranked")
    players = [
        {"discord_user_id": 10, "display_name": "A", "origin": "discord", "opponent_name": "B"},
        {"discord_user_id": 20, "display_name": "B", "origin": "discord", "opponent_name": "A"},
    ]
    session = _table_session({"players": SEATS, "replayUrl": REPLAY})
    with patch("services.sorcery_online_matchmaking.aiohttp.ClientSession", return_value=session):
        await provision_match_and_publish_results(1, pairing_id, "limited", players)
    assert get_pairing_replay(pairing_id) is None
