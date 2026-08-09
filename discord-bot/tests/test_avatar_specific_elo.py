"""Tests for opt-in avatar-specific event Elo."""

import datetime
import sqlite3

import pytest

import repositories.elo_repo as elo_repo
from repositories.elo_repo import (
    create_db,
    create_events_table,
    create_ladder_challenge_table,
    create_match_records_archive,
    get_event_avatar_standings,
    get_qualifying_event_entries,
    get_top_16_user_ids,
    migrate_to_dual_elo_system,
)
from services.elo_service import (
    _calculate_both_elo_changes,
    _calculate_simultaneous_elo_changes,
    correct_match_record,
    end_current_event,
    recalculate_event_elo,
    record_match,
    remove_match_record,
)
from utils.avatar_elo import canonicalize_avatar_name, suggest_avatar_names


def test_avatar_format_preserves_standard_lifetime_elo_math():
    standard = _calculate_both_elo_changes(
        1600, 1500, 1400, 1500, 16, 1.0, 1.0
    )
    avatar = _calculate_simultaneous_elo_changes(
        1600, 1500, 1400, 1500, 16, 1.0, 1.0
    )

    assert avatar[0] == standard[0]
    assert avatar[2] == standard[2]
    assert avatar[1] == 8
    assert avatar[3] == -8


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


@pytest.mark.asyncio
async def test_avatar_ladder_replay_matches_live_multi_match_ratings(avatar_event):
    matches = [
        (1, "Alice", "Impostor", 2, "Bob", "Battlemage"),
        (2, "Bob", "Battlemage", 1, "Alice", "Persecutor"),
        (1, "Alice", "Impostor", 2, "Bob", "Battlemage"),
    ]
    for index, (
        winner_id,
        winner_name,
        winner_avatar,
        loser_id,
        loser_name,
        loser_avatar,
    ) in enumerate(matches):
        await record_match(
            reporter_id=winner_id,
            winner_id=winner_id,
            winner_global=winner_name,
            loser_id=loser_id,
            loser_global=loser_name,
            first_player="y",
            match_time=30,
            match_comment="",
            winner_deck_url=None,
            loser_deck_url=None,
            winner_went_first="y",
            loser_went_first="n",
            winner_avatar=winner_avatar,
            loser_avatar=loser_avatar,
            elo_multiplier_winner=2.0 if index == 0 else 1.0,
            elo_multiplier_loser=0.5 if index == 0 else 1.0,
        )

    conn = sqlite3.connect("match_records.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS admin_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        admin_id INTEGER NOT NULL,
        admin_name TEXT NOT NULL,
        action TEXT NOT NULL,
        target_id TEXT,
        target_name TEXT,
        previous_state TEXT,
        new_state TEXT,
        details TEXT
    )""")
    conn.execute(
        """INSERT INTO admin_audit_log
           (timestamp, admin_id, admin_name, action, target_id, target_name, new_state)
           VALUES (?, 99, 'Admin', 'spot_elo_reset', '2', 'Bob', ?)""",
        (
            datetime.datetime.now().isoformat(),
            '{"event_elo": 1700, "avatar": "Battlemage"}',
        ),
    )
    conn.commit()
    conn.close()
    conn = sqlite3.connect("elo.db")
    conn.execute(
        """UPDATE event_avatar_standings SET event_elo = 1700
           WHERE event_id = 1 AND user_id = '2' AND avatar_name = 'Battlemage'"""
    )
    conn.commit()
    conn.close()

    live = {
        (row["user_id"], row["avatar_name"]): row["event_elo"]
        for row in get_event_avatar_standings(1)
    }
    conn = sqlite3.connect("elo.db")
    conn.execute("UPDATE event_avatar_standings SET event_elo = 999")
    conn.commit()
    conn.close()

    result = recalculate_event_elo()
    replayed = {
        (row["user_id"], row["avatar_name"]): row["event_elo"]
        for row in get_event_avatar_standings(1)
    }

    assert result["matches_replayed"] == 3
    assert replayed == live


@pytest.mark.asyncio
async def test_corrected_avatar_challenge_reapplies_stakes_for_the_new_result(
    avatar_event,
):
    create_ladder_challenge_table()
    conn = sqlite3.connect("match_records.db")
    challenge_id = conn.execute(
        """INSERT INTO ladder_challenges
           (challenger_id, status, created_at,
            winner_elo_multiplier, loser_elo_multiplier)
           VALUES (1, 'open', ?, 2.0, 0.5)""",
        (datetime.datetime.now().isoformat(),),
    ).lastrowid
    conn.commit()
    conn.close()

    match_id, *_ = await record_match(
        reporter_id=2,
        winner_id=2,
        winner_global="Bob",
        loser_id=1,
        loser_global="Alice",
        first_player="y",
        match_time=30,
        match_comment="",
        winner_deck_url=None,
        loser_deck_url=None,
        winner_went_first="y",
        loser_went_first="n",
        winner_avatar="Battlemage",
        loser_avatar="Impostor",
        elo_multiplier_winner=2.0,
        elo_multiplier_loser=0.5,
    )
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        """UPDATE ladder_challenges
           SET status = 'completed', winner_id = 2, match_id = ?
           WHERE challenge_id = ?""",
        (match_id, challenge_id),
    )
    conn.commit()
    conn.close()

    correct_match_record(match_id)

    standings = {
        (row["user_id"], row["avatar_name"]): row["event_elo"]
        for row in get_event_avatar_standings(1)
    }
    assert standings == {
        ("1", "Impostor"): 1508,
        ("2", "Battlemage"): 1492,
    }
    conn = sqlite3.connect("match_records.db")
    stored = conn.execute(
        """SELECT winner_id, winner_elo_multiplier, loser_elo_multiplier
           FROM match_records WHERE rowid = ?""",
        (match_id,),
    ).fetchone()
    conn.close()
    assert stored == (1, 1.0, 1.0)


def test_avatar_free_text_accepts_common_alias_and_suggests_typos(avatar_event):
    assert canonicalize_avatar_name("imposter") == "Impostor"
    assert suggest_avatar_names("Battlemag") == ["Battlemage"]
