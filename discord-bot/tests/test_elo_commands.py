import datetime
import os
import sys
import pytest
import types
from unittest.mock import AsyncMock, patch


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "config" not in sys.modules:
    fake_config = types.ModuleType("config")
    defaults = {
        "MASTERS_ROLE_IDS": [],
        "OPENAI_API_KEY": "test-key",
        "DM_BACKUP_CHANNEL_ID": 0,
        "DM_DISABLED_ROLE_ID": 0,
        "DM_DISABLED_CHANNEL_ID": 0,
        "GUILD_ID": 0,
        "ACTIVE_PLAYER_ROLE_ID": 0,
        "MILESTONE_CHANNEL_ID": 0,
        "LFG_CHANNEL_ID": 0,
        "LEADERBOARD_CHANNEL_ID": 0,
        "TICKET_HOLDER_ROLE_IDS": [],
        "BOT_ADMIN_ROLE_ID": 0,
        "JUDGE_ROLE_ID": 0,
    }
    for key, value in defaults.items():
        setattr(fake_config, key, value)
    sys.modules["config"] = fake_config

from cogs.elo import EloCog


async def _run_match_elo(cog, ctx, match_id):
    await cog.match_elo.callback(cog, ctx, match_id)


class TestMatchEloCommand:
    @patch("cogs.elo.get_current_event_match_elo_snapshot")
    @pytest.mark.asyncio
    async def test_match_elo_command_sends_snapshot(self, mock_snapshot, mock_bot, mock_ctx):
        mock_snapshot.return_value = {
            "match_id": 42,
            "event_name": "Test Event",
            "match_timestamp": datetime.datetime(2026, 1, 2, 3, 4),
            "winner_display_name": "Winner",
            "loser_display_name": "Loser",
            "winner": {
                "lifetime_before": None,
                "lifetime_after": None,
                "event_before": 1600,
                "event_after": 1612,
            },
            "loser": {
                "lifetime_before": None,
                "lifetime_after": None,
                "event_before": 1550,
                "event_after": 1538,
            },
            "notes": ["Accounts for 1 prior manual event Elo reset(s) affecting these players."],
        }
        cog = EloCog(mock_bot)
        mock_ctx.send = AsyncMock()

        await _run_match_elo(cog, mock_ctx, "42")

        sent_message = mock_ctx.send.await_args_list[0].args[0]
        assert "Match #42 Elo Snapshot" in sent_message
        assert "Lifetime: unavailable" in sent_message
        assert "1600 -> 1612" in sent_message

    @pytest.mark.asyncio
    async def test_match_elo_command_rejects_invalid_match_id(self, mock_bot, mock_ctx):
        cog = EloCog(mock_bot)
        mock_ctx.send = AsyncMock()

        await _run_match_elo(cog, mock_ctx, "abc")

        assert "Invalid match ID" in mock_ctx.send.await_args_list[0].args[0]
