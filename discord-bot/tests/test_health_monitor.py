"""Tests for the HealthMonitorCog."""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord

from cogs.health_monitor import (
    HealthMonitorCog, SLOW_RESPONSE_MS, ALERT_COOLDOWN_SECONDS, _status_label,
)


@pytest.fixture
def bot():
    b = MagicMock()
    b.fetch_user = AsyncMock()
    b.wait_until_ready = AsyncMock()
    return b


@pytest.fixture
def cog(bot):
    with patch.object(HealthMonitorCog, "health_check_loop"):
        c = HealthMonitorCog(bot)
    return c


@pytest.mark.asyncio
async def test_check_endpoint_success(cog):
    """Healthy endpoint returns status and response_ms."""
    with patch("cogs.health_monitor.aiohttp.ClientSession") as mock_session_cls:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_cls.return_value = mock_session

        result = await cog._check_endpoint("Test", "http://localhost/health")
        assert result["name"] == "Test"
        assert result["status"] == 200
        assert result["error"] is None
        assert result["response_ms"] is not None


@pytest.mark.asyncio
async def test_check_endpoint_timeout(cog):
    """Timed-out endpoint returns timeout error."""
    with patch("cogs.health_monitor.aiohttp.ClientSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_cls.return_value = mock_session

        result = await cog._check_endpoint("Test", "http://localhost/health")
        assert result["error"] == "timeout"
        assert result["status"] is None


@pytest.mark.asyncio
async def test_check_endpoint_connection_refused(cog):
    """Connection refused returns connection_refused error."""
    import aiohttp
    with patch("cogs.health_monitor.aiohttp.ClientSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError("Connection refused")
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_cls.return_value = mock_session

        result = await cog._check_endpoint("Test", "http://localhost/health")
        assert result["error"] == "connection_refused"


@pytest.mark.asyncio
async def test_dm_owner_sends_message(cog, bot):
    """DM owner sends a message to the configured owner."""
    mock_owner = AsyncMock()
    bot.fetch_user.return_value = mock_owner

    with patch("cogs.health_monitor.config") as mock_config:
        mock_config.OWNER_ID = 12345
        await cog._dm_owner("Test alert")

    bot.fetch_user.assert_called_once_with(12345)
    mock_owner.send.assert_called_once_with("Test alert")


@pytest.mark.asyncio
async def test_dm_owner_skips_when_no_owner_id(cog, bot):
    """DM owner does nothing when OWNER_ID is 0."""
    with patch("cogs.health_monitor.config") as mock_config:
        mock_config.OWNER_ID = 0
        await cog._dm_owner("Test alert")

    bot.fetch_user.assert_not_called()


def test_should_alert_respects_cooldown(cog):
    """Alert cooldown prevents duplicate alerts."""
    assert cog._should_alert("Web App") is True

    cog._record_alert("Web App")
    assert cog._should_alert("Web App") is False

    # Simulate cooldown elapsed
    cog._last_alerts["Web App"] = time.time() - ALERT_COOLDOWN_SECONDS - 1
    assert cog._should_alert("Web App") is True


def test_consecutive_failures_reset_on_success(cog):
    """Consecutive failure counter resets properly."""
    cog._consecutive_failures["Web App"] = 5
    cog._consecutive_failures["Web App"] = 0
    assert cog._consecutive_failures["Web App"] == 0


def test_status_label_ok():
    result = {"status": 200, "response_ms": 50, "error": None, "accept_statuses": set()}
    label, healthy = _status_label(result)
    assert label == "OK"
    assert healthy is True


def test_status_label_accepted_non_200():
    """401/403 are healthy when in accept_statuses (e.g. auth-gated PSO relay)."""
    result = {"status": 403, "response_ms": 20, "error": None, "accept_statuses": {401, 403}}
    label, healthy = _status_label(result)
    assert label == "OK"
    assert healthy is True


def test_status_label_down():
    result = {"status": None, "response_ms": None, "error": "timeout", "accept_statuses": set()}
    label, healthy = _status_label(result)
    assert label == "DOWN"
    assert healthy is False


def test_status_label_slow():
    result = {"status": 200, "response_ms": SLOW_RESPONSE_MS + 100, "error": None, "accept_statuses": set()}
    label, healthy = _status_label(result)
    assert label == "SLOW"
    assert healthy is False


def test_status_label_server_error():
    result = {"status": 502, "response_ms": 100, "error": None, "accept_statuses": set()}
    label, healthy = _status_label(result)
    assert "ERROR" in label
    assert healthy is False


@pytest.mark.asyncio
async def test_recovery_alert_sent(cog):
    """Recovery DM is sent when service comes back after failures."""
    cog._consecutive_failures["Web App"] = 3
    cog._dm_owner = AsyncMock()

    result = {"name": "Web App", "status": 200, "response_ms": 50, "error": None, "accept_statuses": set()}
    service = result["name"]

    if cog._consecutive_failures.get(service, 0) >= 2:
        if cog._should_alert(service):
            await cog._dm_owner(
                f"**{service} has RECOVERED**\n"
                f"Response time: {result['response_ms']}ms | HTTP {result['status']}"
            )
            cog._record_alert(service)
        cog._consecutive_failures[service] = 0

    cog._dm_owner.assert_called_once()
    assert "RECOVERED" in cog._dm_owner.call_args[0][0]
    assert cog._consecutive_failures["Web App"] == 0


@pytest.mark.asyncio
async def test_health_command_owner_gets_report(cog):
    """Owner can use !health to get an on-demand report."""
    cog._build_health_report = AsyncMock(
        return_value=discord.Embed(title="Summit Health Report")
    )

    ctx = AsyncMock()
    ctx.author.id = 12345
    ctx.send = AsyncMock()

    with patch("cogs.health_monitor.config") as mock_config:
        mock_config.OWNER_ID = 12345
        await cog.health_command.callback(cog, ctx)

    cog._build_health_report.assert_called_once()
    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert embed.title == "Summit Health Report"


@pytest.mark.asyncio
async def test_health_command_non_owner_ignored(cog):
    """Non-owner gets no response from !health."""
    ctx = AsyncMock()
    ctx.author.id = 99999
    ctx.send = AsyncMock()

    with patch("cogs.health_monitor.config") as mock_config:
        mock_config.OWNER_ID = 12345
        await cog.health_command.callback(cog, ctx)

    ctx.send.assert_not_called()


@pytest.mark.asyncio
async def test_build_health_report_all_healthy(cog):
    """Health report embed is green when all services healthy."""
    cog._run_checks = AsyncMock(return_value=[
        {"name": "Web App - Leaderboard", "method": "GET", "url": "http://test/api/leaderboard",
         "status": 200, "response_ms": 100, "error": None, "accept_statuses": {200}},
        {"name": "Bot API - Status", "method": "GET", "url": "http://test/users/0/status",
         "status": 200, "response_ms": 50, "error": None, "accept_statuses": {200}},
    ])
    embed = await cog._build_health_report()
    assert embed.color == discord.Color.green()
    assert len(embed.fields) == 2
    assert "OK" in embed.fields[0].name
    assert "OK" in embed.fields[1].name


@pytest.mark.asyncio
async def test_build_health_report_service_down(cog):
    """Health report embed is red when a service is down."""
    cog._run_checks = AsyncMock(return_value=[
        {"name": "Web App - Leaderboard", "method": "GET", "url": "http://test/api/leaderboard",
         "status": None, "response_ms": None, "error": "timeout", "accept_statuses": {200}},
        {"name": "Bot API - Status", "method": "GET", "url": "http://test/users/0/status",
         "status": 200, "response_ms": 50, "error": None, "accept_statuses": {200}},
    ])
    embed = await cog._build_health_report()
    assert embed.color == discord.Color.red()
    assert "DOWN" in embed.fields[0].name


@pytest.mark.asyncio
async def test_build_health_report_shows_urls(cog):
    """Health report includes endpoint URLs for debugging."""
    cog._run_checks = AsyncMock(return_value=[
        {"name": "Web App - Leaderboard", "method": "GET", "url": "http://test/api/leaderboard",
         "status": 200, "response_ms": 100, "error": None, "accept_statuses": {200}},
    ])
    embed = await cog._build_health_report()
    assert "GET http://test/api/leaderboard" in embed.fields[0].value
