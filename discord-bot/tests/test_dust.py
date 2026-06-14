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
    add_alter_card_prize,
    get_available_alter_card,
    claim_alter_card,
    get_alter_card_count,
)
from services.dust_service import (
    validate_dust_code,
    donate_code,
    try_dust_drop,
    try_alter_card_drop,
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
        game_num, chance, locked = increment_game_counter()
        assert game_num == 1
        assert chance == pytest.approx(0.0002)
        assert not locked

        game_num, chance, locked = increment_game_counter()
        assert game_num == 2
        assert chance == pytest.approx(0.0004)

    def test_game_counter_resets_at_100(self):
        for _ in range(99):
            increment_game_counter()
        # Game 100 should trigger reset
        game_num, chance, locked = increment_game_counter()
        assert game_num == 100
        assert chance == pytest.approx(0.02)  # capped at 2%

        # Next game should be 1 (counter reset)
        game_num, chance, locked = increment_game_counter()
        assert game_num == 1
        assert chance == pytest.approx(0.0002)
        assert not locked

    def test_locked_after_drop(self):
        increment_game_counter()
        record_drop(1)
        game_num, chance, locked = increment_game_counter()
        assert game_num == 2
        assert locked

    def test_lock_resets_at_100(self):
        record_drop(1)
        for _ in range(100):
            increment_game_counter()
        # After reset, should be unlocked
        game_num, chance, locked = increment_game_counter()
        assert game_num == 1
        assert not locked

    def test_record_drop_and_status(self):
        record_drop(42)
        status = get_drop_status()
        assert status["last_drop_game"] == 42

    def test_get_drop_status(self):
        status = get_drop_status()
        assert status["games_since_reset"] == 0
        assert status["current_chance"] == "0.02%"
        assert status["last_drop_game"] is None
        assert not status["dropped_this_cycle"]

    def test_get_drop_status_locked(self):
        record_drop(5)
        status = get_drop_status()
        assert status["current_chance"] == "LOCKED"
        assert status["dropped_this_cycle"]


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

    def test_invalid_mixed_group_sizes(self):
        assert not validate_dust_code("1111 22222 33333 44444")

    def test_valid_5_groups_of_4(self):
        assert validate_dust_code("1111 2222 3333 4444 5555")

    def test_valid_5_groups_of_4_with_whitespace(self):
        assert validate_dust_code("  1111 2222 3333 4444 5555  ")

    def test_invalid_5_groups_of_5(self):
        assert not validate_dust_code("11111 22222 33333 44444 55555")

    def test_invalid_4_groups_of_4(self):
        assert not validate_dust_code("1111 2222 3333 4444")

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

    @patch("services.dust_service.random.random", return_value=0.0001)
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

    @patch("services.dust_service.random.random", return_value=0.0001)
    def test_drop_skips_if_both_claimed(self, mock_random):
        add_dust_code("11111 11111 11111 11111", 300, "Donor")
        add_dust_code("22222 22222 22222 22222", 300, "Donor")
        add_dust_code("33333 33333 33333 33333", 300, "Donor")
        # Both players claim codes
        claim_next_code(100, "P1", "Season 1")
        claim_next_code(200, "P2", "Season 1")
        result = try_dust_drop(100, "P1", 200, "P2", "Season 1")
        assert result is None

    @patch("services.dust_service.random.random", return_value=0.0001)
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

    @patch("services.dust_service.random.random", return_value=0.0001)
    def test_one_code_per_season(self, mock_random):
        add_dust_code("11111 11111 11111 11111", 300, "Donor")
        add_dust_code("22222 22222 22222 22222", 300, "Donor")
        # P1 wins in Season 1
        claim_next_code(100, "P1", "Season 1")
        # P1 is eligible in Season 2
        result = try_dust_drop(100, "P1", 200, "P2", "Season 2")
        assert result is not None


# ── Alter Card Repository Tests ──


class TestAlterCardRepo:
    def test_add_and_count(self):
        assert get_alter_card_count() == 0
        add_alter_card_prize("Foil Dragon", 100, "Admin")
        assert get_alter_card_count() == 1

    def test_get_available_alter_card(self):
        assert get_available_alter_card() is None
        add_alter_card_prize("Foil Dragon", 100, "Admin")
        card = get_available_alter_card()
        assert card is not None
        assert card["description"] == "Foil Dragon"

    def test_claim_alter_card(self):
        add_alter_card_prize("Foil Dragon", 100, "Admin")
        card = get_available_alter_card()
        desc = claim_alter_card(card["id"], 200, "Winner")
        assert desc == "Foil Dragon"
        assert get_alter_card_count() == 0
        assert get_available_alter_card() is None

    def test_claim_already_won(self):
        add_alter_card_prize("Foil Dragon", 100, "Admin")
        card = get_available_alter_card()
        claim_alter_card(card["id"], 200, "Winner")
        result = claim_alter_card(card["id"], 300, "Other")
        assert result is None


# ── Alter Card Service Tests ──


class TestTryAlterCardDrop:
    def test_no_drop_when_no_prize(self):
        result = try_alter_card_drop(100, "P1", 200, "P2")
        assert result is None

    @patch("services.dust_service.random.random", return_value=0.0001)
    @patch("services.dust_service.random.choice", return_value=(100, "P1"))
    def test_drop_succeeds(self, mock_choice, mock_random):
        add_alter_card_prize("Foil Dragon", 300, "Admin")
        result = try_alter_card_drop(100, "P1", 200, "P2")
        assert result is not None
        winner_id, winner_name, description = result
        assert winner_id == 100
        assert description == "Foil Dragon"
        assert get_alter_card_count() == 0

    @patch("services.dust_service.random.random", return_value=0.999)
    def test_drop_fails_on_bad_roll(self, mock_random):
        add_alter_card_prize("Foil Dragon", 300, "Admin")
        result = try_alter_card_drop(100, "P1", 200, "P2")
        assert result is None
        assert get_alter_card_count() == 1

    @patch("services.dust_service.random.random", return_value=0.0001)
    @patch("services.dust_service.random.choice", return_value=(100, "P1"))
    def test_no_season_cap(self, mock_choice, mock_random):
        """Alter cards have no season cap - same player can win multiple times."""
        add_alter_card_prize("Foil Dragon", 300, "Admin")
        add_alter_card_prize("Foil Phoenix", 300, "Admin")
        result1 = try_alter_card_drop(100, "P1", 200, "P2")
        assert result1 is not None
        result2 = try_alter_card_drop(100, "P1", 200, "P2")
        assert result2 is not None
        assert result2[2] == "Foil Phoenix"
