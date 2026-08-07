"""Tests for opt-in avatar-specific event Elo."""

import datetime
import sqlite3

import pytest

import repositories.elo_repo as elo_repo
from repositories.elo_repo import (
    create_db,
    create_events_table,
    create_match_records_archive,
    get_event_avatar_standings,
    get_qualifying_event_entries,
    get_top_16_user_ids,
    migrate_to_dual_elo_system,
)
from services.elo_service import (
    correct_match_record,
    end_current_event,
    record_match,
    remove_match_record,
)


@pytest.fixture
def avatar_event(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    elo_repo._dual_elo_migrated = False
    create_db()
    create_events_table()
    create_match_records_archive()
    migrate_to_dual_elo_system()

    conn = sqlite3.connect("elo.db")
    conn.execute("CREATE TABLE card_catalog (name TEXT, card_type TEXT)")
    conn.executemany(
        "INSERT INTO card_catalog (name, card_type) VALUES (?, 'Avatar')",
        [("Impostor",), ("Persecutor",), ("Battlemage",)],
    )
    conn.execute(
        """INSERT INTO events (event_name, start_date, is_active, avatar_specific)
           VALUES ('Avatar League', ?, 1, 1)""",
        (datetime.datetime.now().isoformat(),),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_each_avatar_starts_at_1500_while_lifetime_remains_per_player(avatar_event):
    await record_match(
        reporter_id=1,
        winner_id=1,
        winner_global="Alice",
        loser_id=2,
        loser_global="Bob",
        first_player="y",
        match_time=30,
        match_comment="",
        winner_deck_url=None,
        loser_deck_url=None,
        winner_went_first="y",
        loser_went_first="n",
        winner_avatar="Impostor",
        loser_avatar="Battlemage",
    )
    await record_match(
        reporter_id=1,
        winner_id=1,
        winner_global="Alice",
        loser_id=2,
        loser_global="Bob",
        first_player="y",
        match_time=30,
        match_comment="",
        winner_deck_url=None,
        loser_deck_url=None,
        winner_went_first="y",
        loser_went_first="n",
        winner_avatar="Persecutor",
        loser_avatar="Battlemage",
    )

    standings = get_event_avatar_standings(1)
    ratings = {(row["user_id"], row["avatar_name"]): row["event_elo"] for row in standings}
    assert ratings[("1", "Impostor")] == 1508
    assert ratings[("1", "Persecutor")] == 1508
    assert ratings[("2", "Battlemage")] < 1500

    conn = sqlite3.connect("elo.db")
    alice_lifetime, alice_legacy_event = conn.execute(
        "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id = 1"
    ).fetchone()
    conn.close()
    assert alice_lifetime > 1516
    assert alice_legacy_event == 1500


def test_top_cut_counts_unique_players_but_keeps_their_qualifying_avatars(avatar_event):
    conn = sqlite3.connect("elo.db")
    rows = [
        (1, "online", "1", "Alice", "Impostor", 1700),
        (1, "online", "1", "Alice", "Persecutor", 1690),
    ]
    rows.extend(
        (1, "online", str(user_id), f"Player {user_id}", "Battlemage", 1690 - user_id)
        for user_id in range(2, 17)
    )
    conn.executemany(
        """INSERT INTO event_avatar_standings
           (event_id, source, user_id, user_display_name, avatar_name, event_elo)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()

    qualifying = get_qualifying_event_entries(1, "online", 16)
    alice_avatars = [row["avatar_name"] for row in qualifying if row["user_id"] == "1"]
    assert alice_avatars == ["Impostor", "Persecutor"]
    assert len(get_top_16_user_ids()) == 16


@pytest.mark.asyncio
async def test_avatar_event_rejects_an_unknown_manual_avatar(avatar_event):
    with pytest.raises(ValueError, match="catalog-valid avatars"):
        await record_match(
            reporter_id=1,
            winner_id=1,
            winner_global="Alice",
            loser_id=2,
            loser_global="Bob",
            first_player="y",
            match_time=30,
            match_comment="",
            winner_deck_url=None,
            loser_deck_url=None,
            winner_went_first="y",
            loser_went_first="n",
            winner_avatar="Not A Real Avatar",
            loser_avatar="Battlemage",
        )


@pytest.mark.asyncio
async def test_avatar_is_detected_from_curiosa_json(avatar_event, monkeypatch):
    deck_json = '{"avatar": [{"name": "Impostor", "type": "Avatar"}]}'

    async def fake_scrape(_url):
        return deck_json

    monkeypatch.setattr("services.elo_service.scrape_curosa_async", fake_scrape)
    await record_match(
        reporter_id=1,
        winner_id=1,
        winner_global="Alice",
        loser_id=2,
        loser_global="Bob",
        first_player="y",
        match_time=30,
        match_comment="",
        winner_deck_url="https://curiosa.io/decks/winner",
        loser_deck_url="https://curiosa.io/decks/loser",
        winner_went_first="y",
        loser_went_first="n",
    )

    rows = get_event_avatar_standings(1)
    assert {(row["user_id"], row["avatar_name"]) for row in rows} == {
        ("1", "Impostor"),
        ("2", "Impostor"),
    }


@pytest.mark.asyncio
async def test_remove_and_correct_rebuild_avatar_standings(avatar_event):
    match_id, *_ = await record_match(
        reporter_id=1,
        winner_id=1,
        winner_global="Alice",
        loser_id=2,
        loser_global="Bob",
        first_player="y",
        match_time=30,
        match_comment="",
        winner_deck_url=None,
        loser_deck_url=None,
        winner_went_first="y",
        loser_went_first="n",
        winner_avatar="Impostor",
        loser_avatar="Battlemage",
    )

    correct_match_record(match_id)
    corrected = get_event_avatar_standings(1)
    ratings = {(row["user_id"], row["avatar_name"]): row["event_elo"] for row in corrected}
    assert ratings[("2", "Battlemage")] > 1500
    assert ratings[("1", "Impostor")] < 1500

    remove_match_record(match_id)
    assert get_event_avatar_standings(1) == []


@pytest.mark.asyncio
async def test_ending_event_retains_avatar_rows_for_archived_leaderboard(avatar_event):
    await record_match(
        reporter_id=1,
        winner_id=1,
        winner_global="Alice",
        loser_id=2,
        loser_global="Bob",
        first_player="y",
        match_time=30,
        match_comment="",
        winner_deck_url=None,
        loser_deck_url=None,
        winner_went_first="y",
        loser_went_first="n",
        winner_avatar="Impostor",
        loser_avatar="Battlemage",
    )

    summary = end_current_event()
    assert summary["total_players"] == 2
    assert len(get_event_avatar_standings(1)) == 2

    conn = sqlite3.connect("match_records.db")
    archived = conn.execute(
        "SELECT winner_avatar, loser_avatar FROM match_records_archive"
    ).fetchone()
    conn.close()
    assert archived == ("Impostor", "Battlemage")
