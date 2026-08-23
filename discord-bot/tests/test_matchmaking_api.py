import time
import sys
from unittest.mock import MagicMock, patch

from aiohttp import web
import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg import state
from cogs.lfg.queue_definitions import enabled_queue_definitions
from services.matchmaking_api import _prune_results, _summit_member


def test_enabled_queue_definitions_are_pilot_driven():
    with patch("cogs.lfg.queue_definitions.is_pilot_active", side_effect=lambda pilot: pilot in {"RankedQueue", "GrewWolves"}):
        definitions = enabled_queue_definitions()
    assert [definition["type"] for definition in definitions] == ["ranked", "limited"]
    assert definitions[1]["deck_mode"] == "active_run"


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
