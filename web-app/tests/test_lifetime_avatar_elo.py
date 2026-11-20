"""Lifetime avatar ELO (Glicko-2 per player and avatar, first Glicko-2 season on).

Shown on the profile (lifetime ELO visibility), the player avatar page (to
everyone) and the avatar leaderboard's ``scope=lifetime``. Provisional entries
(< 8 games) show no rating and take no rank. Before the first Glicko-2 season
the table is missing and every view shows nothing new.
"""

import sqlite3

from services import glicko2_season as g2
from tests.conftest import seed_elo_data

DAY = "2027-01-02"


def _freeze(elo_db):
    """The switch to Glicko-2 lifetime, which creates lifetime_avatar_standings."""
    conn = sqlite3.connect(str(elo_db))
    g2.freeze_lifetime(conn, "2027-01-01T00:00:00")
    conn.commit()
    conn.close()


def _seed_lifetime(elo_db, rows):
    """rows: (user_id, avatar, name, elo, games)."""
    _freeze(elo_db)
    conn = sqlite3.connect(str(elo_db))
    conn.executemany(
        "INSERT INTO lifetime_avatar_standings (user_id, avatar, user_display_name, elo, rating, games) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(uid, avatar, name, elo, float(elo), games) for uid, avatar, name, elo, games in rows],
    )
    conn.commit()
    conn.close()


LADDER = [
    # Witch: 1 and 2 settled (2 rated higher), 3 provisional
    (1, "Witch", "Ann", 1580, 12),
    (2, "Witch", "Bo", 1620, 8),
    (3, "Witch", "Cy", 1700, 3),
    (1, "Pathfinder", "Ann", 1490, 5),
]


def test_nothing_new_before_the_first_glicko2_season(admin_session, elo_db, match_db):
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Ann"}])

    profile = admin_session.get("/api/player/1").get_json()
    assert profile["lifetime_avatar_elo"] == []

    page = admin_session.get("/api/player/1/avatar/Witch").get_json()
    assert page["lifetime_avatar_elo"] is None

    board = admin_session.get("/api/leaderboard/avatars?scope=lifetime").get_json()
    assert board["success"] is True and board["scope"] == "lifetime"
    assert board["avatars"] == []


def test_profile_lists_lifetime_avatar_elo_with_ranks(admin_session, elo_db, match_db):
    seed_elo_data(elo_db, [{"user_id": u, "name": n} for u, n in (("1", "Ann"), ("2", "Bo"), ("3", "Cy"))])
    _seed_lifetime(elo_db, LADDER)

    ann = admin_session.get("/api/player/1").get_json()["lifetime_avatar_elo"]
    # Most played first
    assert ann == [
        {"avatar": "Witch", "elo": 1580, "games": 12, "rank": 2,
         "provisional": False, "provisional_games": 12},
        {"avatar": "Pathfinder", "elo": None, "games": 5, "rank": None,
         "provisional": True, "provisional_games": 5},
    ]

    # Cy's 1700 is provisional: no rating, no rank, and Bo still ranks first
    cy = admin_session.get("/api/player/3").get_json()["lifetime_avatar_elo"]
    assert cy == [{"avatar": "Witch", "elo": None, "games": 3, "rank": None,
                   "provisional": True, "provisional_games": 3}]
    bo = admin_session.get("/api/player/2").get_json()["lifetime_avatar_elo"]
    assert bo[0]["rank"] == 1 and bo[0]["elo"] == 1620


def test_profile_lifetime_avatar_elo_follows_lifetime_visibility(client, elo_db, match_db):
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Ann"}, {"user_id": "77", "name": "Reg"}])
    _seed_lifetime(elo_db, LADDER + [(77, "Witch", "Reg", 1550, 9)])

    # A visitor sees no lifetime ratings, avatar ones included
    assert client.get("/api/player/1").get_json()["lifetime_avatar_elo"] == []

    # The owner sees their own
    with client.session_transaction() as sess:
        sess["user_id"] = "77"
        sess["username"] = "RegularUser"
    own = client.get("/api/player/77").get_json()["lifetime_avatar_elo"]
    assert own == [{"avatar": "Witch", "elo": 1550, "games": 9, "rank": 3,
                    "provisional": False, "provisional_games": 9}]


def test_player_avatar_page_shows_the_entry_to_everyone(client, elo_db, match_db):
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Ann"}])
    _seed_lifetime(elo_db, LADDER)

    page = client.get("/api/player/1/avatar/witch").get_json()
    assert page["lifetime_avatar_elo"] == {
        "avatar": "Witch", "elo": 1580, "games": 12, "rank": 2,
        "provisional": False, "provisional_games": 12,
    }
    provisional = client.get("/api/player/1/avatar/Pathfinder").get_json()["lifetime_avatar_elo"]
    assert provisional["elo"] is None and provisional["provisional"] is True
    assert provisional["provisional_games"] == 5
    assert client.get("/api/player/1/avatar/Sorcerer").get_json()["lifetime_avatar_elo"] is None


def test_lifetime_avatar_leaderboard_settled_first(client, elo_db, match_db):
    _seed_lifetime(elo_db, LADDER)

    data = client.get("/api/leaderboard/avatars?scope=lifetime&min_games=0").get_json()

    assert data["success"] is True and data["scope"] == "lifetime"
    assert data["provisional_games_needed"] == 8
    by_avatar = {a["avatar"]: a for a in data["avatars"]}
    witch = by_avatar["Witch"]
    assert witch["players"] == 3
    assert [(e["user_id"], e["elo"], e["rank"]) for e in witch["entries"]] == [
        ("2", 1620, 1), ("1", 1580, 2), ("3", None, None),
    ]
    assert witch["entries"][2]["provisional"] is True
    assert witch["entries"][2]["provisional_games"] == 3
    assert all(e["overall_rank"] is None for e in witch["entries"])
    assert by_avatar["Pathfinder"]["entries"][0]["rank"] is None

    # One avatar only, and the season view stays the default
    one = client.get("/api/leaderboard/avatars?scope=lifetime&avatar=witch").get_json()
    assert [a["avatar"] for a in one["avatars"]] == ["Witch"]
    assert client.get("/api/leaderboard/avatars").get_json()["scope"] == "season"
    assert client.get("/api/leaderboard/avatars?scope=forever").status_code == 400


def _seed_avatar_match(match_db, winner, w_avatar, loser, l_avatar, ts):
    """A Glicko-2 lifetime match in the real match_records layout (after migrations)."""
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, winner_elo_change, losser_id, losser_display_name,
            loser_elo_change, timestamp, source, match_type, winner_avatar, loser_avatar,
            rating_system, lifetime_system)
           VALUES (?, ?, 0, ?, ?, 0, ?, 'Discord', 'ranked', ?, ?, 'glicko2', 'glicko2')""",
        (winner, f"P{winner}", loser, f"P{loser}", ts, w_avatar, l_avatar),
    )
    conn.commit()
    conn.close()


def test_matches_rated_by_the_module_reach_the_ladder(client, elo_db, match_db):
    seed_elo_data(elo_db, [{"user_id": u, "name": f"P{u}"} for u in ("1", "2")])
    _freeze(elo_db)
    # 9 games Witch (1) v Pathfinder (2): 1 wins 7, 2 wins 2
    for i in range(9):
        winner, loser = ("2", "1") if i in (3, 6) else ("1", "2")
        avatars = {"1": "Witch", "2": "Pathfinder"}
        _seed_avatar_match(match_db, winner, avatars[winner], loser, avatars[loser], f"{DAY}T10:{i:02d}:00")
    elo_conn, match_conn = sqlite3.connect(str(elo_db)), sqlite3.connect(str(match_db))
    g2.rebuild_lifetime(elo_conn, match_conn)
    elo_conn.commit()
    match_conn.commit()
    elo_conn.close()
    match_conn.close()

    data = client.get("/api/leaderboard/avatars?scope=lifetime&min_games=0").get_json()
    witch = {a["avatar"]: a for a in data["avatars"]}["Witch"]["entries"][0]
    assert witch["user_id"] == "1" and witch["games"] == 9
    assert (witch["wins"], witch["losses"]) == (7, 2)
    assert witch["rank"] == 1 and isinstance(witch["elo"], int) and witch["elo"] > 1500

    page = client.get("/api/player/2/avatar/Pathfinder").get_json()["lifetime_avatar_elo"]
    assert page["games"] == 9 and page["rank"] == 1 and page["elo"] < 1500
