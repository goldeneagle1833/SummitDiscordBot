"""Replay links on a player's profile match history follow the replay privacy rule."""

import sqlite3

from repositories.user_profiles import UserProfileRepository
from tests.conftest import seed_elo_data, seed_matches

REPLAY = "https://playsorceryonline.com/replay/abc123"


def _seed(match_db, elo_db):
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Alice"}, {"user_id": "2", "name": "Bob"}])
    seed_matches(match_db, [{"winner_id": "1", "loser_id": "2", "timestamp": "2026-10-14 12:00:00"}])
    conn = sqlite3.connect(str(match_db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(match_records)")}
    if "replay_url" not in cols:
        conn.execute("ALTER TABLE match_records ADD COLUMN replay_url TEXT")
    conn.execute("UPDATE match_records SET replay_url = ?", (REPLAY,))
    conn.commit()
    conn.close()


def _profile_replays(client, player_id="1"):
    resp = client.get(f"/api/player/{player_id}")
    assert resp.status_code == 200
    return [m["replay_url"] for m in resp.get_json()["matches"]]


def _as(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_profile_replay_visible_to_its_players_only(client, match_db, elo_db):
    _seed(match_db, elo_db)
    assert _profile_replays(client) == [None]  # logged out
    _as(client, "1")
    assert _profile_replays(client) == [REPLAY]
    _as(client, "2")  # the opponent viewing the winner's profile
    assert _profile_replays(client) == [REPLAY]
    _as(client, "3")
    assert _profile_replays(client) == [None]


def test_profile_replay_public_when_both_players_opt_in(client, match_db, elo_db):
    _seed(match_db, elo_db)
    conn = sqlite3.connect(str(match_db))
    for user_id in ("1", "2"):
        conn.execute(
            "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
            " VALUES (?, 'discord', 'P', 'now', 'now')",
            (user_id,),
        )
    conn.commit()
    conn.close()
    repo = UserProfileRepository(match_db)
    repo.set_profile_visibility("1", {"replays": True})
    assert _profile_replays(client) == [None]  # only one player opted in
    repo.set_profile_visibility("2", {"replays": True})
    assert _profile_replays(client) == [REPLAY]
