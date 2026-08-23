"""Tests for Limited queue (arena draft mode) system.

Covers:
- Arena run lifecycle (create → update → complete at 2L and 4W)
- Limited ELO calculation (K=32, start at 1500)
- Forfeit ELO penalty (phantom losses against starting ELO)
- Starting new run after completed/forfeited run (US-6)
- Queue isolation (limited only matches limited)
"""

import pytest
import sqlite3
import os
import sys
import types
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "config" not in sys.modules:
    fake_config = types.ModuleType("config")
    defaults = {
        "OPENAI_API_KEY": "test-key",
        "DM_BACKUP_CHANNEL_ID": 0,
        "DM_DISABLED_ROLE_ID": 0,
        "DM_DISABLED_CHANNEL_ID": 0,
        "GUILD_ID": 0,
        "ACTIVE_PLAYER_ROLE_ID": 0,
        "MILESTONE_CHANNEL_ID": 0,
        "LFG_CHANNEL_ID": 0,
    }
    for key, value in defaults.items():
        setattr(fake_config, key, value)
    sys.modules["config"] = fake_config

from repositories.limited_repo import (
    create_limited_tables,
    create_arena_run,
    get_active_arena_run,
    get_arena_run,
    update_arena_run_record,
    complete_arena_run,
    get_limited_elo,
    get_limited_lifetime_elo,
    upsert_limited_elo,
    get_all_limited_standings,
    save_limited_pairing,
    get_limited_pairing_between_players,
    mark_limited_pairing_reported,
    cleanup_old_limited_pairings,
    insert_limited_match_record,
    reset_limited_elo_to_default,
)
from services.limited_service import (
    update_limited_elo,
    start_arena_run,
    check_run_complete,
    get_run_summary,
    forfeit_arena_run,
    limited_winner_report,
)
from services.elo_service import update_elo
from cogs.lfg.state import lfg_queue
from cogs.lfg.queue import (
    JoinQueueButtons,
    LimitedQueueModal,
    LIMITED_RUN_REQUIRED_MESSAGE,
)


# --- Fixtures ---


@pytest.fixture(autouse=True)
def setup_limited_tables():
    """Ensure limited tables exist for each test."""
    create_limited_tables()
    yield


# --- Arena Run Lifecycle Tests ---


class TestArenaRunLifecycle:
    """Test arena run creation, updates, and completion."""

    def test_create_arena_run(self):
        run_id = create_arena_run(100, "Player1", "https://curiosa.io/deck/123", "{}", 1500)
        assert run_id is not None
        run = get_arena_run(run_id)
        assert run is not None
        assert run["user_id"] == 100
        assert run["wins"] == 0
        assert run["losses"] == 0
        assert run["status"] == "active"
        assert run["deck_url"] == "https://curiosa.io/deck/123"

    def test_get_active_arena_run(self):
        run_id = create_arena_run(200, "Player2", "https://curiosa.io/deck/456", "{}", 1500)
        active = get_active_arena_run(200)
        assert active is not None
        assert active["run_id"] == run_id

    def test_no_active_run_initially(self):
        active = get_active_arena_run(999)
        assert active is None

    def test_update_arena_run_record(self):
        run_id = create_arena_run(300, "Player3", "https://curiosa.io/deck/789", "{}", 1500)
        update_arena_run_record(run_id, 2, 1)
        run = get_arena_run(run_id)
        assert run is not None
        assert run["wins"] == 2
        assert run["losses"] == 1

    def test_complete_at_two_losses(self):
        run_id = create_arena_run(400, "Player4", "https://curiosa.io/deck/a", "{}", 1500)
        update_arena_run_record(run_id, 1, 2)
        completed = check_run_complete(run_id)
        assert completed is True
        run = get_arena_run(run_id)
        assert run is not None
        assert run["status"] == "completed"

    def test_complete_at_four_wins(self):
        run_id = create_arena_run(500, "Player5", "https://curiosa.io/deck/b", "{}", 1500)
        update_arena_run_record(run_id, 4, 1)
        completed = check_run_complete(run_id)
        assert completed is True
        run = get_arena_run(run_id)
        assert run is not None
        assert run["status"] == "completed"

    def test_not_complete_at_one_loss(self):
        run_id = create_arena_run(600, "Player6", "https://curiosa.io/deck/c", "{}", 1500)
        update_arena_run_record(run_id, 2, 1)
        completed = check_run_complete(run_id)
        assert completed is False
        run = get_arena_run(run_id)
        assert run is not None
        assert run["status"] == "active"

    @patch("services.limited_service.get_active_event", return_value={"event_id": 1, "event_name": "Test", "start_date": "2025-01-01"})
    def test_start_new_run_after_completed(self, mock_event):
        """US-6: Can start a new run after previous one completes."""
        run_id_1 = create_arena_run(700, "Player7", "https://curiosa.io/deck/d1", "{}", 1500)
        update_arena_run_record(run_id_1, 4, 0)
        complete_arena_run(run_id_1, "completed")

        # Should be able to start a new run
        run = start_arena_run(700, "Player7", "https://curiosa.io/deck/d2")
        assert run is not None
        assert run["run_id"] != run_id_1
        assert run["wins"] == 0
        assert run["losses"] == 0

    @patch("services.limited_service.get_active_event", return_value={"event_id": 1, "event_name": "Test", "start_date": "2025-01-01"})
    def test_cannot_start_run_with_active_run(self, mock_event):
        """Cannot start a new run while one is active."""
        create_arena_run(800, "Player8", "https://curiosa.io/deck/e", "{}", 1500)
        with pytest.raises(ValueError, match="already has an active arena run"):
            start_arena_run(800, "Player8", "https://curiosa.io/deck/f")


# --- Limited ELO Tests ---


class TestLimitedElo:
    """Test limited ELO system (separate from main ELO)."""

    def test_default_elo_is_1500(self):
        elo = get_limited_elo(9001)
        assert elo == 1500

    def test_upsert_limited_elo(self):
        upsert_limited_elo(9002, "EloPlayer", 1600)
        elo = get_limited_elo(9002)
        assert elo == 1600

    def test_update_limited_elo_win(self):
        """Winner's ELO should increase."""
        # Start both at 1500
        new_elo, change = update_limited_elo(1001, "Winner", True, 1002)
        assert change > 0
        assert new_elo > 1500

    def test_update_limited_elo_loss(self):
        """Loser's ELO should decrease."""
        new_elo, change = update_limited_elo(1003, "Loser", False, 1004)
        assert change < 0
        assert new_elo < 1500

    def test_limited_elo_uses_k32(self):
        """K=32 is used for limited ELO. Equal players: change should be ~16."""
        new_elo, change = update_limited_elo(2001, "P1", True, 2002)
        assert abs(change) == 16  # K/2 = 32/2 for equal-rated players

    def test_limited_elo_independent_from_main(self):
        """Limited ELO changes don't affect main ELO."""
        # Set up main ELO
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO overall_standings (user_id, user_display_name, online_elo) VALUES (?, ?, ?)",
            (3001, "MainPlayer", 1700),
        )
        conn.commit()
        conn.close()

        # Update limited ELO
        update_limited_elo(3001, "MainPlayer", True, 3002)

        # Main ELO should be unchanged
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute("SELECT online_elo FROM overall_standings WHERE user_id = ?", (3001,))
        main_elo = cur.fetchone()[0]
        conn.close()
        assert main_elo == 1700


# --- Lifetime ELO Tests ---


class TestLifetimeElo:
    """Test lifetime ELO tracking (never resets across seasons)."""

    def test_default_lifetime_elo_is_1500(self):
        elo = get_limited_lifetime_elo(8001)
        assert elo == 1500

    def test_lifetime_elo_updates_with_match(self):
        """Lifetime ELO should change when a match is reported."""
        new_elo, change = update_limited_elo(8002, "LTPlayer", True, 8003)
        lifetime = get_limited_lifetime_elo(8002)
        assert lifetime == 1500 + change

    def test_lifetime_elo_preserved_on_season_reset(self):
        """Season reset should not affect lifetime ELO."""
        update_limited_elo(8004, "LTPreserve", True, 8005)
        lifetime_before = get_limited_lifetime_elo(8004)
        assert lifetime_before != 1500

        reset_limited_elo_to_default()

        season_elo = get_limited_elo(8004)
        lifetime_after = get_limited_lifetime_elo(8004)
        assert season_elo == 1500
        assert lifetime_after == lifetime_before

    def test_lifetime_elo_accumulates(self):
        """Lifetime ELO should accumulate across multiple matches."""
        update_limited_elo(8006, "Accum", True, 8007)
        lt1 = get_limited_lifetime_elo(8006)
        update_limited_elo(8006, "Accum", True, 8008)
        lt2 = get_limited_lifetime_elo(8006)
        assert lt2 > lt1

    def test_standings_include_lifetime_elo(self):
        """get_all_limited_standings should include lifetime_elo."""
        upsert_limited_elo(8009, "StandingsP", 1600, elo_change=100)
        standings = get_all_limited_standings()
        player = next((s for s in standings if s["user_id"] == 8009), None)
        assert player is not None
        assert "lifetime_elo" in player
        assert player["lifetime_elo"] == 1600

    def test_admin_spot_fix_does_not_affect_lifetime(self):
        """upsert without elo_change should not touch lifetime_elo."""
        upsert_limited_elo(8010, "SpotFix", 1600, elo_change=100)
        lt_before = get_limited_lifetime_elo(8010)
        # Admin spot fix (no elo_change)
        upsert_limited_elo(8010, "SpotFix", 1700)
        lt_after = get_limited_lifetime_elo(8010)
        assert lt_after == lt_before
        assert get_limited_elo(8010) == 1700


# --- Forfeit Tests ---


class TestForfeit:
    """Test forfeit mechanics and ELO penalty."""

    def test_forfeit_applies_remaining_losses(self):
        """Forfeit with 1 loss should apply 1 more phantom loss."""
        run_id = create_arena_run(4001, "ForfeitP", "https://curiosa.io/deck/f1", "{}", 1500)
        update_arena_run_record(run_id, 2, 1)

        summary = forfeit_arena_run(4001)
        run = get_arena_run(run_id)
        assert run is not None

        assert run["status"] == "forfeited"
        assert run["losses"] == 2  # Updated to 2
        assert "Forfeited" in summary

        # ELO should have dropped (1 phantom loss)
        elo = get_limited_elo(4001)
        assert elo < 1500

    def test_forfeit_with_zero_losses(self):
        """Forfeit with 0 losses applies 2 phantom losses."""
        run_id = create_arena_run(4002, "ForfeitP2", "https://curiosa.io/deck/f2", "{}", 1500)

        forfeit_arena_run(4002)
        elo = get_limited_elo(4002)

        # 2 phantom losses from 1500 vs 1500 starting
        assert elo < 1500

    def test_forfeit_no_active_run_raises(self):
        """Forfeit without active run should raise ValueError."""
        with pytest.raises(ValueError, match="no active arena run"):
            forfeit_arena_run(4003)

    @patch("services.limited_service.get_active_event", return_value={"event_id": 1, "event_name": "Test", "start_date": "2025-01-01"})
    def test_start_new_run_after_forfeit(self, mock_event):
        """Can start a new run after forfeiting."""
        run_id = create_arena_run(4004, "ForfeitP3", "https://curiosa.io/deck/f3", "{}", 1500)
        forfeit_arena_run(4004)

        new_run = start_arena_run(4004, "ForfeitP3", "https://curiosa.io/deck/f4")
        assert new_run is not None
        assert new_run["run_id"] != run_id

    def test_forfeit_penalty_sequential(self):
        """Phantom losses are applied sequentially (each against current ELO, not starting)."""
        run_id = create_arena_run(4005, "SeqP", "https://curiosa.io/deck/f5", "{}", 1500)
        # Give them some wins first to test against starting ELO
        update_arena_run_record(run_id, 3, 0)
        # Update their ELO to reflect the wins
        upsert_limited_elo(4005, "SeqP", 1548)

        forfeit_arena_run(4005)
        final_elo = get_limited_elo(4005)

        # Should be less than 1548 (2 phantom losses applied)
        assert final_elo < 1548


# --- Limited Pairing Tests ---


class TestLimitedPairings:
    """Test limited-specific pairing operations."""

    def test_save_and_get_limited_pairing(self):
        save_limited_pairing(111, 5001, 5002, "url1", "url2", 10, 20)
        pairing = get_limited_pairing_between_players(111, 5001, 5002)
        assert pairing is not None

    def test_mark_limited_pairing_reported(self):
        save_limited_pairing(111, 5003, 5004, "url3", "url4", 30, 40)
        mark_limited_pairing_reported(111, 5003, 5004)
        pairing = get_limited_pairing_between_players(111, 5003, 5004)
        assert pairing is None  # Should be gone after marked as reported

    def test_limited_pairing_not_found_for_nonexistent(self):
        pairing = get_limited_pairing_between_players(111, 9998, 9999)
        assert pairing is None


# --- Limited Match Record Tests ---


class TestLimitedMatchRecord:
    """Test limited match recording."""

    def test_insert_limited_match_record(self):
        match_id = insert_limited_match_record(
            reporter_id=6001,
            winner_id=6001,
            winner_display_name="Winner",
            loser_id=6002,
            loser_display_name="Loser",
            did_win=True,
            first_player="Winner",
            match_time=15,
            curiosa_url_winner="url_w",
            curiosa_url_loser="url_l",
            match_comment="GG",
            json_deck_data_winner="{}",
            json_deck_data_loser="{}",
            winner_elo_change=16,
            loser_elo_change=-16,
            winner_went_first="Yes",
            loser_went_first="No",
            winner_run_id=1,
            loser_run_id=2,
        )
        assert match_id is not None

        # Verify it's in the limited table, not main
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("SELECT * FROM limited_match_records WHERE match_id = ?", (match_id,))
        row = cur.fetchone()
        conn.close()
        assert row is not None

    def test_limited_match_not_in_main_table(self):
        """Limited matches should NOT appear in the main match_records table."""
        match_id = insert_limited_match_record(
            reporter_id=6003,
            winner_id=6003,
            winner_display_name="LimitedW",
            loser_id=6004,
            loser_display_name="LimitedL",
            did_win=True,
            first_player="LimitedW",
            match_time=20,
            curiosa_url_winner="",
            curiosa_url_loser="",
            match_comment="",
            json_deck_data_winner="{}",
            json_deck_data_loser="{}",
            winner_elo_change=16,
            loser_elo_change=-16,
            winner_went_first="Yes",
            loser_went_first="No",
            winner_run_id=None,
            loser_run_id=None,
        )
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM match_records WHERE winner_id = ?", (6003,))
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0  # Not in main table


# --- Limited Winner Report Integration Tests ---


class TestLimitedWinnerReport:
    """Test the integrated limited_winner_report function."""

    @patch("services.limited_service.get_active_event", return_value={"event_id": 1, "event_name": "Test", "start_date": "2025-01-01"})
    def test_limited_winner_report_updates_runs(self, mock_event):
        """Report should increment winner wins and loser losses."""
        w_run = create_arena_run(7001, "W", "url_w", "{}", 1500)
        l_run = create_arena_run(7002, "L", "url_l", "{}", 1500)

        match_id, w_complete, l_complete, w_elo_change, l_elo_change = limited_winner_report(
            reporter_id=7001,
            winner_id=7001,
            winner_display_name="W",
            loser_id=7002,
            loser_display_name="L",
            first_player="W",
            match_time=10,
            curiosa_url_winner="url_w",
            curiosa_url_loser="url_l",
            match_comment="test",
            winner_went_first="Yes",
            loser_went_first="No",
            winner_run_id=w_run,
            loser_run_id=l_run,
        )

        assert match_id is not None
        assert w_complete is False
        assert l_complete is False
        assert w_elo_change > 0
        assert l_elo_change < 0

        w_run_data = get_arena_run(w_run)
        l_run_data = get_arena_run(l_run)
        assert w_run_data is not None
        assert l_run_data is not None
        assert w_run_data["wins"] == 1
        assert l_run_data["losses"] == 1

    @patch("services.limited_service.get_active_event", return_value={"event_id": 1, "event_name": "Test", "start_date": "2025-01-01"})
    def test_limited_winner_report_completes_at_threshold(self, mock_event):
        """Run should auto-complete when hitting 4W or 2L threshold."""
        w_run = create_arena_run(7003, "W2", "url_w2", "{}", 1500)
        l_run = create_arena_run(7004, "L2", "url_l2", "{}", 1500)

        # Set winner to 3 wins (will become 4 after report)
        update_arena_run_record(w_run, 3, 0)
        # Set loser to 1 loss (will become 2 after report)
        update_arena_run_record(l_run, 1, 1)

        _, w_complete, l_complete, _, _ = limited_winner_report(
            reporter_id=7003,
            winner_id=7003,
            winner_display_name="W2",
            loser_id=7004,
            loser_display_name="L2",
            first_player="W2",
            match_time=10,
            curiosa_url_winner="",
            curiosa_url_loser="",
            match_comment="",
            winner_went_first="Yes",
            loser_went_first="No",
            winner_run_id=w_run,
            loser_run_id=l_run,
        )

        assert w_complete is True
        assert l_complete is True


# --- Queue Isolation Tests ---


class TestQueueIsolation:
    """Test that limited queue entries only match with other limited entries."""

    def test_limited_only_matches_limited(self):
        from cogs.lfg.cog import LFGCog
        assert LFGCog.are_queue_types_compatible("limited", "limited") is True

    def test_limited_does_not_match_ranked(self):
        from cogs.lfg.cog import LFGCog
        assert LFGCog.are_queue_types_compatible("limited", "ranked") is False

    def test_limited_does_not_match_testing(self):
        from cogs.lfg.cog import LFGCog
        assert LFGCog.are_queue_types_compatible("limited", "testing") is False

    def test_limited_does_not_match_both(self):
        from cogs.lfg.cog import LFGCog
        assert LFGCog.are_queue_types_compatible("limited", "both") is False

    def test_ranked_does_not_match_limited(self):
        from cogs.lfg.cog import LFGCog
        assert LFGCog.are_queue_types_compatible("ranked", "limited") is False

    def test_resolve_match_type_limited(self):
        from cogs.lfg.cog import LFGCog
        assert LFGCog.resolve_match_type("limited", "limited") == "limited"


# --- Run Summary Tests ---


class TestRunSummary:
    """Test run summary formatting."""

    def test_get_run_summary_active(self):
        run_id = create_arena_run(8001, "SumP", "https://curiosa.io/deck/s1", "{}", 1500)
        update_arena_run_record(run_id, 3, 1)
        summary = get_run_summary(run_id)
        assert "3-1" in summary
        assert "In Progress" in summary
        assert "curiosa.io" in summary

    def test_get_run_summary_completed(self):
        run_id = create_arena_run(8002, "SumP2", "https://curiosa.io/deck/s2", "{}", 1500)
        update_arena_run_record(run_id, 4, 1)
        complete_arena_run(run_id, "completed")
        summary = get_run_summary(run_id)
        assert "4-1" in summary
        assert "Completed" in summary

    def test_get_run_summary_not_found(self):
        summary = get_run_summary(99999)
        assert "not found" in summary.lower()


class TestLimitedQueueJoinModal:
    """Test Limited queue modal behavior."""

    @pytest.fixture(autouse=True)
    def clear_lfg_queue(self):
        lfg_queue.clear()
        yield
        lfg_queue.clear()

    @pytest.mark.asyncio
    async def test_join_limited_button_uses_limited_modal(self, mock_bot, mock_interaction):
        view = JoinQueueButtons(mock_bot)

        with patch("cogs.lfg.queue.queue_is_enabled", return_value=True):
            await view._handle_join(mock_interaction, "limited")

        modal = mock_interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, LimitedQueueModal)
        assert len(modal.children) == 1
        assert len(modal.children) == 1

    @pytest.mark.asyncio
    async def test_limited_modal_queues_with_active_run_data(self, mock_bot, mock_interaction):
        create_arena_run(
            mock_interaction.user.id,
            "TestUser",
            "https://curiosa.io/deck/limited-run",
            "{}",
            1500,
        )

        lfg_cog = MagicMock()
        lfg_cog.clean_expired_lfg = MagicMock()
        lfg_cog.check_if_someone_is_lfg = MagicMock(return_value=None)
        lfg_cog.add_to_lfg_queue = MagicMock()
        lfg_cog.update_lfg_status = AsyncMock()
        mock_bot.get_cog.return_value = lfg_cog

        modal = LimitedQueueModal(mock_bot)
        modal.timeframe._value = "45"

        await modal.on_submit(mock_interaction)

        lfg_cog.add_to_lfg_queue.assert_called_once()
        _, timeframe_value, deck_url, queue_type = lfg_cog.add_to_lfg_queue.call_args.args[:4]
        assert timeframe_value == 45
        assert deck_url == "https://curiosa.io/deck/limited-run"
        assert queue_type == "limited"
        assert lfg_cog.add_to_lfg_queue.call_args.kwargs["run_id"] > 0
        mock_interaction.followup.send.assert_awaited_with(
            "You've joined the **Limited** queue for 45 minutes!\n**Deck:** https://curiosa.io/deck/limited-run",
            ephemeral=True,
        )

    @pytest.mark.asyncio
    async def test_limited_modal_requires_active_run(self, mock_bot, mock_interaction):
        mock_bot.get_cog.return_value = MagicMock()
        modal = LimitedQueueModal(mock_bot)
        modal.timeframe._value = "30"

        await modal.on_submit(mock_interaction)

        mock_interaction.followup.send.assert_awaited_with(
            LIMITED_RUN_REQUIRED_MESSAGE,
            ephemeral=True,
        )

    @pytest.mark.asyncio
    async def test_limited_modal_requires_new_run_after_completed_run(self, mock_bot, mock_interaction):
        run_id = create_arena_run(
            mock_interaction.user.id,
            "TestUser",
            "https://curiosa.io/deck/completed-run",
            "{}",
            1500,
        )
        complete_arena_run(run_id, "completed")

        mock_bot.get_cog.return_value = MagicMock()
        modal = LimitedQueueModal(mock_bot)
        modal.timeframe._value = "30"

        await modal.on_submit(mock_interaction)

        mock_interaction.followup.send.assert_awaited_with(
            LIMITED_RUN_REQUIRED_MESSAGE,
            ephemeral=True,
        )
