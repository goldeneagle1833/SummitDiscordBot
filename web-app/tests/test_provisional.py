"""Provisional Glicko-2 ratings: no rating, rank or per-game change until settled."""

import sqlite3

from services import glicko2_season as g2
from tests.conftest import seed_elo_data

EVENT_ID = 9
DAY = "2027-01-02"


def _start_event(elo_db, system="glicko2"):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode, rating_system) "
        "VALUES (?, 'Season 9', '2027-01-01T00:00:00', 1, 'player', ?)",
        (EVENT_ID, system),
    )
    conn.commit()
    conn.close()


def _seed_match(match_db, winner, loser, ts, system="glicko2"):
    """A rated match in the real match_records layout (after the startup migration)."""
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, winner_elo_change, losser_id, losser_display_name,
            loser_elo_change, timestamp, source, match_type,
            winner_lifetime_elo_change, loser_lifetime_elo_change, event_id, rating_system,
            lifetime_system)
           VALUES (?, ?, 16, ?, ?, -16, ?, 'Discord', 'ranked', 16, -16, ?, ?, ?)""",
        (winner, f"P{winner}", loser, f"P{loser}", ts, EVENT_ID, system,
         "glicko2" if system == "glicko2" else None),
    )
    conn.commit()
    conn.close()


def _rebuild(elo_db, match_db, lifetime=False):
    elo_conn, match_conn = sqlite3.connect(str(elo_db)), sqlite3.connect(str(match_db))
    try:
        g2.rebuild_season(elo_conn, match_conn, g2.get_event(elo_conn))
        if lifetime:
            g2.rebuild_lifetime(elo_conn, match_conn)
        elo_conn.commit()
        match_conn.commit()
    finally:
        elo_conn.close()
        match_conn.close()


def _freeze_lifetime(elo_db):
    conn = sqlite3.connect(str(elo_db))
    g2.freeze_lifetime(conn, "2027-01-01T00:00:00")
    conn.commit()
    conn.close()


def _season(client, elo_db, match_db, lifetime=False):
    """Players 1 and 2 play 8 games (settled), 3 and 4 play 7 (provisional)."""
    _start_event(elo_db)
    seed_elo_data(elo_db, [
        {"user_id": u, "name": f"P{u}", "online_elo": 1600 + int(u)} for u in ("1", "2", "3", "4")
    ])
    if lifetime:
        _freeze_lifetime(elo_db)
    for i in range(8):
        _seed_match(match_db, "1" if i % 4 else "2", "2" if i % 4 else "1", f"{DAY}T10:{i:02d}:00")
    for i in range(7):
        _seed_match(match_db, "3", "4", f"{DAY}T11:{i:02d}:00")
    _rebuild(elo_db, match_db, lifetime)


def test_event_leaderboard_hides_provisional_ratings(client, elo_db, match_db):
    _season(client, elo_db, match_db)

    data = client.get("/api/leaderboard/event").get_json()

    assert data["provisional_games_needed"] == 8
    rows = data["leaderboard"]
    # Settled players first, by rating, ranked among themselves
    assert [r["id"] for r in rows[:2]] == sorted(["1", "2"], key=lambda u: -next(
        r["event_elo"] for r in rows if r["id"] == u))
    for row in rows[:2]:
        assert isinstance(row["event_elo"], int)
        assert row["provisional"] is False and row["provisional_games"] == 8
    assert [r["rank"] for r in rows[:2]] == [1, 2]
    # Then provisional ones: no rating, no rank
    for row in rows[2:]:
        assert row["id"] in ("3", "4")
        assert row["event_elo"] is None and row["rank"] is None
        assert row["provisional"] is True and row["provisional_games"] == 7

    combined = client.get("/api/leaderboard/combined").get_json()["event"]["leaderboard"]
    assert {r["id"]: r["event_elo"] is None for r in combined} == {
        "1": False, "2": False, "3": True, "4": True,
    }


def test_profile_masks_provisional_rating_and_changes(admin_session, elo_db, match_db):
    _season(admin_session, elo_db, match_db, lifetime=True)

    data = admin_session.get("/api/player/3?event=current").get_json()

    assert data["event_elo"] is None and data["online_event_elo"] is None
    assert data["event_provisional"] is True and data["event_provisional_games"] == 7
    assert data["displayed_elo"] is None and data["displayed_rank"] is None
    assert data["displayed_provisional"] is True
    assert data["legacy_elo"] == 1603  # Seasons 1-8 lifetime, frozen at the switch
    assert data["elo"] is None and data["lifetime_provisional"] is True
    assert data["matches"] and all(
        m["elo_change"] is None and m["elo_change_hidden"] for m in data["matches"]
    )
    # Lifetime chart points from provisional games are left out
    assert data["elo_history"] == []

    settled = admin_session.get("/api/player/1?event=current").get_json()
    assert isinstance(settled["event_elo"], int) and settled["event_provisional"] is False
    assert settled["displayed_rank"] in (1, 2)
    assert settled["legacy_elo"] == 1601


def test_match_history_shows_changes_from_the_ninth_game(client, elo_db, match_db):
    _start_event(elo_db)
    seed_elo_data(elo_db, [{"user_id": u, "name": f"P{u}"} for u in ("1", "2")])
    for i in range(9):
        _seed_match(match_db, "1", "2", f"{DAY}T10:{i:02d}:00")
    _rebuild(elo_db, match_db)

    matches = client.get(f"/api/match-history?date={DAY}").get_json()

    assert len(matches) == 9
    ninth = max(matches, key=lambda m: m["timestamp"])
    assert isinstance(ninth["winner_elo_change"], (int, float))
    assert "winner_elo_change_hidden" not in ninth
    for m in matches:
        if m is not ninth:
            assert m["winner_elo_change"] is None and m["winner_elo_change_hidden"] is True
            assert m["loser_elo_change"] is None and m["loser_elo_change_hidden"] is True


def test_elo_seasons_are_unchanged(client, elo_db, match_db):
    _start_event(elo_db, system="elo")
    seed_elo_data(elo_db, [
        {"user_id": "1", "name": "P1", "online_event_elo": 1516},
        {"user_id": "2", "name": "P2", "online_event_elo": 1484},
    ])
    _seed_match(match_db, "1", "2", f"{DAY}T10:00:00", system="elo")

    rows = client.get("/api/leaderboard/event").get_json()["leaderboard"]
    assert [(r["id"], r["event_elo"]) for r in rows] == [("1", 1516), ("2", 1484)]
    assert all("provisional" not in r for r in rows)

    matches = client.get(f"/api/match-history?date={DAY}").get_json()
    assert matches[0]["winner_elo_change"] == 16
    assert "winner_elo_change_hidden" not in matches[0]

    profile = client.get("/api/player/1?event=current").get_json()
    assert profile["event_elo"] == 1516 and "event_provisional" not in profile
    assert profile["matches"][0]["elo_change"] == 16


def test_lifetime_and_archived_boards_hide_provisional_players(client, elo_db, match_db):
    _season(client, elo_db, match_db, lifetime=True)

    lifetime = {r["id"]: r for r in client.get("/api/leaderboard").get_json()}
    assert lifetime["3"]["elo"] is None and lifetime["3"]["rank"] is None
    assert lifetime["3"]["provisional_games"] == 7
    assert isinstance(lifetime["1"]["elo"], int) and lifetime["1"]["rank"] in (1, 2)
    assert client.get("/api/elo-distribution").get_json()["total_players"] == 2

    # End the season: its archive keeps every player's final rating
    conn = sqlite3.connect(str(elo_db))
    conn.execute("UPDATE events SET is_active = 0, end_date = '2027-02-01' WHERE event_id = ?", (EVENT_ID,))
    for uid, elo in conn.execute("SELECT user_id, online_event_elo FROM overall_standings").fetchall():
        conn.execute(
            "INSERT INTO event_standings_archive (event_id, user_id, user_display_name, "
            "final_event_elo, final_rank) VALUES (?, ?, ?, ?, 0)",
            (EVENT_ID, uid, f"P{uid}", elo),
        )
    conn.commit()
    conn.close()

    archived = client.get(f"/api/leaderboard/archived/{EVENT_ID}").get_json()["leaderboard"]
    assert [r["rank"] for r in archived] == [1, 2, None, None]
    assert [r["event_elo"] is None for r in archived] == [False, False, True, True]
    one = client.get(f"/api/player/3/event/{EVENT_ID}").get_json()
    assert one["elo"] is None and one["rank"] is None and one["provisional"] is True
