"""Tests for the dust code reward system."""

import pytest
from unittest.mock import patch

from repositories.dust_repo import (
    create_dust_tables,
    add_dust_code,
    get_available_code_count,
    claim_next_code,
    has_player_claimed_this_season,
    increment_game_counter,
    record_drop,
    get_drop_status,
    code_exists,
)
from services.dust_service import (
    validate_dust_code,
    donate_code,
    try_dust_drop,
)


@pytest.fixture(autouse=True)
def setup_dust_tables():
    """Ensure dust tables exist for every test."""
    create_dust_tables()


# ── Repository Tests ──


class TestDustRepo:
    def test_add_and_count_codes(self):
        assert get_available_code_count() == 0
        add_dust_code("11111 22222 33333 44444", 100, "Donor")
        assert get_available_code_count() == 1
        add_dust_code("55555 66666 77777 88888", 100, "Donor")
        assert get_available_code_count() == 2

    def test_claim_next_code_fifo(self):
        add_dust_code("11111 11111 11111 11111", 100, "Donor")
        add_dust_code("22222 22222 22222 22222", 100, "Donor")
        code = claim_next_code(200, "Player", "Season 1")
        assert code == "11111 11111 11111 11111"
        assert get_available_code_count() == 1

    def test_claim_returns_none_when_empty(self):
        assert claim_next_code(200, "Player", "Season 1") is None

    def test_has_player_claimed_this_season(self):
        add_dust_code("11111 11111 11111 11111", 100, "Donor")
        assert not has_player_claimed_this_season(200, "Season 1")
        claim_next_code(200, "Player", "Season 1")
        assert has_player_claimed_this_season(200, "Season 1")
        assert not has_player_claimed_this_season(200, "Season 2")

    def test_code_exists(self):
        assert not code_exists("11111 11111 11111 11111")
        add_dust_code("11111 11111 11111 11111", 100, "Donor")
        assert code_exists("11111 11111 11111 11111")

    def test_increment_game_counter(self):
        game_num, chance = increment_game_counter()
        assert game_num == 1
        assert chance == pytest.approx(0.005)

        game_num, chance = increment_game_counter()
        assert game_num == 2
        assert chance == pytest.approx(0.01)

    def test_game_counter_resets_at_100(self):
        for _ in range(99):
            increment_game_counter()
        # Game 100 should trigger reset
        game_num, chance = increment_game_counter()
        assert game_num == 100
        assert chance == pytest.approx(0.50)  # capped at 50%

        # Next game should be 1 (counter reset)
        game_num, chance = increment_game_counter()
        assert game_num == 1
        assert chance == pytest.approx(0.005)

    def test_drop_chance_caps_at_50_percent(self):
        # Even though we reset at 100, test the math
        # At game 100: 100 * 0.005 = 0.50 = 50%
        for _ in range(99):
            increment_game_counter()
        game_num, chance = increment_game_counter()
        assert chance == pytest.approx(0.50)

    def test_record_drop_and_status(self):
        record_drop(42)
        status = get_drop_status()
        assert status["last_drop_game"] == 42

    def test_get_drop_status(self):
        status = get_drop_status()
        assert status["games_since_reset"] == 0
        assert status["current_chance"] == "0.0%"
        assert status["last_drop_game"] is None


# ── Service Tests ──


class TestDustCodeValidation:
    def test_valid_code(self):
        assert validate_dust_code("11111 22222 33333 44444")

    def test_valid_code_with_whitespace(self):
        assert validate_dust_code("  11111 22222 33333 44444  ")

    def test_invalid_too_few_groups(self):
        assert not validate_dust_code("11111 22222 33333")

    def test_invalid_letters(self):
        assert not validate_dust_code("abcde 22222 33333 44444")

    def test_invalid_wrong_group_size(self):
        assert not validate_dust_code("1111 22222 33333 44444")

    def test_invalid_extra_groups(self):
        assert not validate_dust_code("11111 22222 33333 44444 55555")

    def test_empty_string(self):
        assert not validate_dust_code("")


class TestDonateCode:
    def test_donate_valid_code(self):
        success, msg = donate_code("11111 22222 33333 44444", 100, "Donor")
        assert success
        assert "accepted" in msg.lower()
        assert get_available_code_count() == 1

    def test_donate_invalid_format(self):
        success, msg = donate_code("bad code", 100, "Donor")
        assert not success
        assert "Invalid format" in msg

    def test_donate_duplicate_code(self):
        donate_code("11111 22222 33333 44444", 100, "Donor")
        success, msg = donate_code("11111 22222 33333 44444", 101, "Donor2")
        assert not success
        assert "already been loaded" in msg


class TestTryDustDrop:
    def test_no_drop_when_no_codes(self):
        result = try_dust_drop(100, "P1", 200, "P2", "Season 1")
        assert result is None

    @patch("services.dust_service.random.random", return_value=0.001)
    @patch("services.dust_service.random.choice", return_value=(100, "P1"))
    def test_drop_succeeds(self, mock_choice, mock_random):
        add_dust_code("11111 22222 33333 44444", 300, "Donor")
        increment_game_counter()  # need at least 1 game for non-zero chance
        result = try_dust_drop(100, "P1", 200, "P2", "Season 1")
        assert result is not None
        winner_id, winner_name, code = result
        assert winner_id == 100
        assert code == "11111 22222 33333 44444"

    @patch("services.dust_service.random.random", return_value=0.999)
    def test_drop_fails_on_bad_roll(self, mock_random):
        add_dust_code("11111 22222 33333 44444", 300, "Donor")
        result = try_dust_drop(100, "P1", 200, "P2", "Season 1")
        assert result is None

    @patch("services.dust_service.random.random", return_value=0.001)
    def test_drop_skips_if_both_claimed(self, mock_random):
        add_dust_code("11111 11111 11111 11111", 300, "Donor")
        add_dust_code("22222 22222 22222 22222", 300, "Donor")
        add_dust_code("33333 33333 33333 33333", 300, "Donor")
        # Both players claim codes
        claim_next_code(100, "P1", "Season 1")
        claim_next_code(200, "P2", "Season 1")
        result = try_dust_drop(100, "P1", 200, "P2", "Season 1")
        assert result is None

    @patch("services.dust_service.random.random", return_value=0.001)
    def test_drop_rerolls_to_eligible_player(self, mock_random):
        add_dust_code("11111 11111 11111 11111", 300, "Donor")
        add_dust_code("22222 22222 22222 22222", 300, "Donor")
        # P1 already claimed
        claim_next_code(100, "P1", "Season 1")
        result = try_dust_drop(100, "P1", 200, "P2", "Season 1")
        assert result is not None
        winner_id, winner_name, code = result
        assert winner_id == 200
        assert winner_name == "P2"

    @patch("services.dust_service.random.random", return_value=0.001)
    def test_one_code_per_season(self, mock_random):
        add_dust_code("11111 11111 11111 11111", 300, "Donor")
        add_dust_code("22222 22222 22222 22222", 300, "Donor")
        # P1 wins in Season 1
        claim_next_code(100, "P1", "Season 1")
        # P1 is eligible in Season 2
        result = try_dust_drop(100, "P1", 200, "P2", "Season 2")
        assert result is not None
