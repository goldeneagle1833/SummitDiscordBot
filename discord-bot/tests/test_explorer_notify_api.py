"""Tests for the Explorer application notification endpoint on the bot API."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
import discord
import pytest

# config.py is gitignored, so it is absent in worktrees and CI.
sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from services.matchmaking_api import start_matchmaking_api

ROUTE = "/explorer-application-notify"

PAYLOAD = {
    "admin_discord_ids": ["111111111111111111"],
    "applicant_name": "Ruben Sanchez",
    "discord_handle": "Rubonic",
    "location": "Mechanicsville, Virginia",
    "lgs_name": "Waterloo Games",
    "review_url": "https://sorcererssummit.com/admin/explorer-applications",
}


async def get_handler(bot):
    """Start the API with the network mocked out and pull one route's handler."""
    runner = MagicMock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    site = MagicMock()
    site.start = AsyncMock()
    with (
        patch("services.matchmaking_api.web.AppRunner", return_value=runner) as app_runner,
        patch("services.matchmaking_api.web.TCPSite", return_value=site),
    ):
        await start_matchmaking_api(bot)

    app = app_runner.call_args[0][0]
    for route in app.router.routes():
        if route.resource.canonical == ROUTE and route.method == "POST":
            return route.handler
    raise AssertionError(f"{ROUTE} is not registered")


def make_request(payload):
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    return request


def forbidden():
    return discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "DMs closed")


def body_of(response):
    return json.loads(response.body)


def make_bot(user=None, fetch_side_effect=None):
    bot = MagicMock()
    if fetch_side_effect is not None:
        bot.fetch_user = AsyncMock(side_effect=fetch_side_effect)
    else:
        bot.fetch_user = AsyncMock(return_value=user or make_user())
    return bot


def make_user(send_side_effect=None):
    user = MagicMock()
    user.send = AsyncMock(side_effect=send_side_effect)
    return user


@pytest.mark.asyncio
async def test_dms_each_admin():
    user = make_user()
    bot = make_bot(user)
    handler = await get_handler(bot)

    payload = {**PAYLOAD, "admin_discord_ids": ["111111111111111111", "222222222222222222"]}
    response = await handler(make_request(payload))

    assert body_of(response)["sent"] == 2
    assert user.send.await_count == 2


@pytest.mark.asyncio
async def test_embed_carries_the_application_summary():
    user = make_user()
    handler = await get_handler(make_bot(user))

    await handler(make_request(PAYLOAD))

    embed = user.send.await_args.kwargs["embed"]
    assert "Ruben Sanchez" in embed.description
    rendered = json.dumps(embed.to_dict())
    assert "Rubonic" in rendered
    assert "Mechanicsville, Virginia" in rendered
    assert "Waterloo Games" in rendered
    assert "/admin/explorer-applications" in rendered


@pytest.mark.asyncio
async def test_a_closed_dm_does_not_stop_the_other_admins():
    # First recipient has DMs off, second should still be told.
    blocked, reachable = make_user(send_side_effect=forbidden()), make_user()
    bot = MagicMock()
    bot.fetch_user = AsyncMock(side_effect=[blocked, reachable])
    handler = await get_handler(bot)

    payload = {**PAYLOAD, "admin_discord_ids": ["1111", "2222"]}
    body = body_of(await handler(make_request(payload)))

    assert body["sent"] == 1
    assert body["results"][0] == {"user_id": "1111", "sent": False, "reason": "dms_disabled"}
    assert body["results"][1]["sent"] is True


@pytest.mark.asyncio
async def test_non_snowflake_admin_is_skipped_not_fatal():
    user = make_user()
    bot = make_bot(user)
    handler = await get_handler(bot)

    payload = {**PAYLOAD, "admin_discord_ids": ["google_12345", "222222222222222222"]}
    body = body_of(await handler(make_request(payload)))

    assert body["sent"] == 1
    assert body["results"][0]["reason"] == "not_discord_id"
    bot.fetch_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_discord_user_is_reported():
    bot = make_bot(fetch_side_effect=discord.NotFound(MagicMock(status=404), "nope"))
    handler = await get_handler(bot)

    body = body_of(await handler(make_request(PAYLOAD)))

    assert body["sent"] == 0
    assert body["results"][0]["reason"] == "user_not_found"


@pytest.mark.asyncio
async def test_empty_recipient_list_is_rejected():
    handler = await get_handler(make_bot())
    with pytest.raises(web.HTTPBadRequest):
        await handler(make_request({**PAYLOAD, "admin_discord_ids": []}))


@pytest.mark.asyncio
async def test_non_json_body_is_rejected():
    handler = await get_handler(make_bot())
    request = MagicMock()
    request.json = AsyncMock(side_effect=ValueError("not json"))
    with pytest.raises(web.HTTPBadRequest):
        await handler(request)
