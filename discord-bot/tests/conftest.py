"""
Shared test fixtures for Discord bot tests.

Provides mock Discord objects, database setup, and common test utilities.
"""

import pytest
import asyncio
import sqlite3
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import repositories.elo_repo as elo_repo

from utils.database import create_db


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def setup_test_databases():
    """Setup and cleanup test databases before each test."""
    elo_repo._dual_elo_migrated = False

    # Remove any existing test databases
    for db_path in ["match_records.db", "elo.db"]:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                pass

    # Create fresh test database
    create_db()

    # Create ELO database
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS overall_standings
           (user_id INTEGER PRIMARY KEY,
            user_display_name TEXT,
            elo INTEGER DEFAULT 1500,
            event_elo INTEGER DEFAULT 1500,
            paper_elo INTEGER DEFAULT 1500,
            online_elo INTEGER DEFAULT 1500,
            paper_event_elo INTEGER DEFAULT 1500,
            online_event_elo INTEGER DEFAULT 1500)"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS events (
           event_id INTEGER PRIMARY KEY AUTOINCREMENT,
           event_name TEXT NOT NULL,
           start_date TEXT NOT NULL,
           end_date TEXT,
           is_active BOOLEAN DEFAULT 1)"""
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS ladder_challenges (
           challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
           challenger_id INTEGER NOT NULL,
           challenged_id INTEGER NOT NULL,
           challenger_rank INTEGER,
           challenged_rank INTEGER,
           stakes_multiplier TEXT DEFAULT 'Normal',
           status TEXT DEFAULT 'pending',
           created_at TEXT NOT NULL,
           expires_at TEXT NOT NULL,
           responded_at TEXT,
           accepted_at TEXT,
           completed_at TEXT,
           winner_id INTEGER,
           match_id INTEGER,
           guild_id INTEGER)"""
    )
    conn.commit()
    conn.close()

    yield  # Run the test

    # Teardown: Clean up test databases
    for db_path in ["match_records.db", "elo.db"]:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                pass


@pytest.fixture
def mock_user():
    """Create a mock Discord User."""
    user = MagicMock()
    user.id = 123456789
    user.global_name = "TestUser"
    user.display_name = "TestUser"
    user.mention = "<@123456789>"
    return user


@pytest.fixture
def mock_user_2():
    """Create a second mock Discord User."""
    user = MagicMock()
    user.id = 987654321
    user.global_name = "OtherUser"
    user.display_name = "OtherUser"
    user.mention = "<@987654321>"
    return user


@pytest.fixture
def mock_guild():
    """Create a mock Discord Guild."""
    guild = MagicMock()
    guild.id = 111111111
    guild.name = "TestGuild"
    return guild


@pytest.fixture
def mock_channel():
    """Create a mock Discord Channel."""
    channel = MagicMock()
    channel.id = 222222222
    channel.name = "test-channel"
    channel.send = AsyncMock()
    return channel


@pytest.fixture
def mock_interaction(mock_user, mock_guild, mock_channel):
    """Create a mock Discord Interaction."""
    interaction = MagicMock()
    interaction.user = mock_user
    interaction.guild = mock_guild
    interaction.channel = mock_channel
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


@pytest.fixture
def mock_bot(mock_user):
    """Create a mock Discord Bot."""
    bot = MagicMock()
    bot.user = mock_user
    bot.user.id = 111222333
    bot.fetch_user = AsyncMock()
    bot.get_cog = MagicMock()
    bot.get_channel = MagicMock()
    bot.get_guild = MagicMock()
    bot.get_context = AsyncMock()
    return bot


@pytest.fixture
def mock_ctx(mock_user, mock_guild, mock_channel, mock_bot):
    """Create a mock Discord Context."""
    ctx = MagicMock()
    ctx.bot = mock_bot
    ctx.author = mock_user
    ctx.guild = mock_guild
    ctx.channel = mock_channel
    ctx.send = AsyncMock()
    ctx.message = MagicMock()
    ctx.message.created_at = datetime.now()
    return ctx


@pytest.fixture
def mock_config():
    """Create mock config values."""
    with patch("config.LFG_CHANNEL_ID", 222222222), patch(
        "config.GUILD_ID", 111111111
    ), patch("config.DM_DISABLED_CHANNEL_ID", 333333333), patch(
        "config.MILESTONE_CHANNEL_ID", 444444444
    ):
        yield
