"""Avatar-mode events on the site: per-avatar ladder, one top-cut slot per player."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

import webapp_config
from migrations.add_avatar_elo_mode import migrate
from repositories.brackets import BracketRepository
from services.brackets import BracketService
from services.ticket_leaderboard import TicketLeaderboardService
from tests.conftest import seed_elo_data


def _start_event(elo_db, mode="avatar", event_id=5):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode) "
        "VALUES (?, 'Avatar Season', '2026-10-01', 1, ?)",
        (event_id, mode),
    )
    conn.commit()
    conn.close()


def _seed_entries(elo_db, rows, event_id=5):
    conn = sqlite3.connect(str(elo_db))
    conn.executemany(
        "INSERT INTO event_avatar_standings "
        "(event_id, user_id, avatar, user_display_name, event_elo, games_played) VALUES (?, ?, ?, ?, ?, ?)",
        [(event_id, *row) for row in rows],
    )
    conn.commit()
    conn.close()


def _seed_avatar_match(match_db, winner, w_avatar, loser, l_avatar, *, w_after, l_after,
                       w_change=16, l_change=-16, w_life=16, l_life=-16, ts="2026-10-02 12:00:00"):
    conn = sqlite3.connect(str(match_db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(match_records)")}
    for col in ("winner_lifetime_elo_change", "loser_lifetime_elo_change"):
        if col not in cols:  # the bot's schema has them; the test fixture doesn't
            conn.execute(f"ALTER TABLE match_records ADD COLUMN {col} INTEGER")
    cur = conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, winner_elo_change, losser_id, losser_display_name,
            loser_elo_change, timestamp, source, match_type,
            winner_lifetime_elo_change, loser_lifetime_elo_change,
            winner_avatar, loser_avatar, winner_avatar_elo_change, loser_avatar_elo_change,
            winner_avatar_elo_after, loser_avatar_elo_after)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'Discord', 'ranked', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (winner, f"P{winner}", w_change, loser, f"P{loser}", l_change, ts, w_life, l_life,
         w_avatar, l_avatar, w_change, l_change, w_after, l_after),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid


@pytest.fixture()
def avatar_db(app, elo_db, match_db):
    """Databases after startup migrations, with an Avatar-mode event running."""
    _start_event(elo_db)
    return elo_db, match_db


# ── Schema ──


def test_migration_adds_the_mode_and_locks_it(elo_db, match_db):
    migrate(elo_db, match_db)
    migrate(elo_db, match_db)  # idempotent
    _start_event(elo_db)
    conn = sqlite3.connect(str(elo_db))
    try:
        with pytest.raises(sqlite3.IntegrityError, match="cannot change"):
            conn.execute("UPDATE events SET elo_mode = 'player' WHERE event_id = 5")
    finally:
        conn.close()
    conn = sqlite3.connect(str(match_db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(match_records)")}
    conn.close()
    assert {"winner_avatar", "loser_avatar_elo_after"} <= cols


# ── Leaderboards ──


def test_event_leaderboard_lists_one_row_per_player_and_avatar(client, avatar_db):
    elo_db, match_db = avatar_db
    _seed_entries(elo_db, [
        ("1", "Imposter", "Alice", 1560, 2),
        ("2", "Witch", "Bob", 1530, 1),
        ("1", "Persecutor", "Alice", 1490, 1),
    ])
    _seed_avatar_match(match_db, "1", "Imposter", "2", "Witch", w_after=1516, l_after=1484)

    data = client.get("/api/leaderboard/event").get_json()

    assert data["event"]["elo_mode"] == "avatar"
    rows = data["leaderboard"]
    assert [(r["id"], r["avatar"]) for r in rows] == [
        ("1", "Imposter"), ("2", "Witch"), ("1", "Persecutor"),
    ]
    assert len({r["entry_id"] for r in rows}) == 3
    assert (rows[0]["wins"], rows[0]["losses"]) == (1, 0)


def test_player_mode_event_is_unchanged(client, elo_db):
    _start_event(elo_db, mode="player")
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Alice", "online_event_elo": 1600}])
    data = client.get("/api/leaderboard/event").get_json()
    assert data["event"]["elo_mode"] == "player"


class FakeLeaderboard:
    def __init__(self, rows):
        self.rows = rows

    def get_event_leaderboard(self):
        return {"event": {"event_id": 5, "event_name": "S", "elo_mode": "avatar"}, "leaderboard": self.rows}

    def get_leaderboard(self):
        return []


def _entry(uid, avatar, elo):
    return {"id": uid, "entry_id": f"{uid}:{avatar}", "name": f"P{uid}", "avatar": avatar,
            "event_elo": elo, "wins": 1, "losses": 0, "voice_games": 0}


LADDER = [_entry("u1", "Imposter", 1600), _entry("u1", "Witch", 1580), _entry("u2", "Seer", 1570)]


def test_ticket_holders_get_one_slot_per_player(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp_config, "DISCORD_BOT_TOKEN", "")
    monkeypatch.setattr(webapp_config, "TICKET_HOLDER_ROLE_IDS", set())
    repo = BracketRepository(db_path=tmp_path / "tickets.db")
    repo.ensure_tables()
    repo.replace_ticket_holders([{"user_id": "u1"}, {"user_id": "u2"}])

    data = TicketLeaderboardService(FakeLeaderboard(LADDER), repo).get_leaderboard()

    assert [(p["user_id"], p["avatar"]) for p in data["ticket_holders"]] == [("u1", "Imposter"), ("u2", "Seer")]
    assert [p["rank"] for p in data["ticket_holders"]] == [1, 2]
    assert len(data["overall"]) == 3  # every entry still shows on the ladder
    assert data["elo_mode"] == "avatar"


def test_bracket_seed_pool_seeds_each_player_once(tmp_path):
    repo = BracketRepository(db_path=tmp_path / "brackets.db")
    repo.ensure_tables()
    service = BracketService(repo=repo, leaderboard_service=FakeLeaderboard(LADDER))
    pool = service.get_seed_pool("overall")
    assert [(p["user_id"], p["avatar"]) for p in pool["players"]] == [("u1", "Imposter"), ("u2", "Seer")]


# ── Profile ──


def test_profile_lists_every_avatar_entry_with_rank_and_history(client, avatar_db):
    elo_db, match_db = avatar_db
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Alice"}, {"user_id": "2", "name": "Bob"}])
    _seed_entries(elo_db, [
        ("2", "Witch", "Bob", 1600, 3),
        ("1", "Imposter", "Alice", 1516, 1),
        ("1", "Persecutor", "Alice", 1484, 1),
    ])
    _seed_avatar_match(match_db, "1", "Imposter", "2", "Witch", w_after=1516, l_after=1484)

    anonymous = client.get("/api/player/1?event=current").get_json()["avatar_event_elo"]
    assert anonymous["history"] == {}  # the graph follows the ELO history privacy setting
    assert len(anonymous["entries"]) == 2  # ratings are public like the ladder

    with client.session_transaction() as sess:
        sess["user_id"] = "1"
    data = client.get("/api/player/1?event=current").get_json()

    block = data["avatar_event_elo"]
    assert block["elo_mode"] == "avatar"
    assert [(e["avatar"], e["event_elo"], e["rank"]) for e in block["entries"]] == [
        ("Imposter", 1516, 2), ("Persecutor", 1484, 3),
    ]
    assert block["history"]["Imposter"][0]["elo"] == 1516


def test_profile_in_player_mode_has_no_avatar_entries(client, elo_db):
    _start_event(elo_db, mode="player")
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Alice"}])
    block = client.get("/api/player/1?event=current").get_json()["avatar_event_elo"]
    assert block["elo_mode"] == "player" and block["entries"] == []


# ── Admin ──


def test_remove_match_reverts_each_ladder_by_its_own_change(admin_session, avatar_db):
    elo_db, match_db = avatar_db
    seed_elo_data(elo_db, [
        {"user_id": "1", "name": "Alice", "online_elo": 1532, "online_event_elo": 1516},
        {"user_id": "2", "name": "Bob", "online_elo": 1468, "online_event_elo": 1484},
    ])
    _seed_entries(elo_db, [("1", "Imposter", "Alice", 1520, 1), ("2", "Witch", "Bob", 1480, 1)])
    match_id = _seed_avatar_match(
        match_db, "1", "Imposter", "2", "Witch", w_after=1520, l_after=1480,
        w_change=16, l_change=-16, w_life=32, l_life=-32,
    )
    # the avatar ladder moved by 20, not 16
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE match_records SET winner_avatar_elo_change = 20, loser_avatar_elo_change = -20")
    conn.commit()
    conn.close()

    resp = admin_session.delete(f"/api/admin/remove-match/{match_id}")
    assert resp.status_code == 200, resp.get_json()

    conn = sqlite3.connect(str(elo_db))
    standings = dict(conn.execute("SELECT user_id, online_elo || '/' || online_event_elo FROM overall_standings"))
    avatars = dict(conn.execute("SELECT user_id, event_elo FROM event_avatar_standings"))
    conn.close()
    assert standings == {"1": "1500/1500", "2": "1500/1500"}
    assert avatars == {1: 1500, 2: 1500}


def test_start_event_passes_the_mode_to_the_bot(admin_session):
    bot_db = MagicMock()
    bot_db.get_active_event.return_value = None
    bot_db.start_new_event.return_value = {"event_id": 9, "previous_event": None}
    with patch("routes.api.admin._import_bot_database_utils", return_value=bot_db):
        resp = admin_session.post("/api/admin/start-event", json={"event_name": "S9", "elo_mode": "avatar"})
        bad = admin_session.post("/api/admin/start-event", json={"event_name": "S9", "elo_mode": "deck"})

    assert resp.status_code == 200
    bot_db.start_new_event.assert_called_once_with("S9", elo_mode="avatar")
    assert bad.status_code == 400


def test_match_history_shows_the_avatar_entry_change(client, avatar_db):
    elo_db, match_db = avatar_db
    seed_elo_data(elo_db, [{"user_id": "1", "name": "Alice"}, {"user_id": "2", "name": "Bob"}])
    _seed_avatar_match(match_db, "1", "Imposter", "2", "Witch", w_after=1512, l_after=1488,
                       w_change=20, l_change=-19)
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE match_records SET winner_avatar_elo_change = 12, loser_avatar_elo_change = -12")
    conn.commit()
    conn.close()

    matches = client.get("/api/player/2?event=current").get_json()["matches"]
    assert [m["elo_change"] for m in matches] == [-12]


# ── Top Players: current season is public ──


def test_top_players_page_lists_the_current_season_for_everyone(client, avatar_db, monkeypatch):
    import routes.api.avatars
    # avatars.py binds the DB path at import time; point it at this test's DB
    monkeypatch.setattr(routes.api.avatars, "ELO_DB_PATH", avatar_db[0])
    everyone = client.get("/api/avatars/filters?include_active=1").get_json()
    assert any(e["is_active"] for e in everyone["events"])
    # Other avatar pages still keep the running season to admins
    default = client.get("/api/avatars/filters").get_json()
    assert not any(e["is_active"] for e in default["events"])


# ── Per-avatar leaderboards (PSO pulls these instead of per-player calls) ──


def test_avatar_leaderboards_split_the_ladder_per_avatar(client, avatar_db):
    elo_db, _ = avatar_db
    _seed_entries(elo_db, [
        ("1", "Imposter", "Alice", 1600, 5),
        ("2", "Witch", "Bob", 1580, 4),
        ("3", "Imposter", "Cara", 1540, 3),
        ("1", "Witch", "Alice", 1490, 2),
    ])

    data = client.get("/api/leaderboard/avatars").get_json()

    assert data["success"] and data["elo_mode"] == "avatar"
    assert [a["avatar"] for a in data["avatars"]] == ["Imposter", "Witch"]
    imposter = data["avatars"][0]
    assert imposter["players"] == 2
    assert [(e["rank"], e["overall_rank"], e["user_id"], e["elo"]) for e in imposter["entries"]] == [
        (1, 1, "1", 1600), (2, 3, "3", 1540),
    ]

    one = client.get("/api/leaderboard/avatars?avatar=witch&limit=1").get_json()
    assert [a["avatar"] for a in one["avatars"]] == ["Witch"]
    assert [e["user_id"] for e in one["avatars"][0]["entries"]] == ["2"]
    assert one["avatars"][0]["players"] == 2

    assert client.get("/api/leaderboard/avatars?limit=0").status_code == 400


def test_avatar_leaderboards_are_empty_in_player_mode(client, elo_db):
    _start_event(elo_db, mode="player")
    data = client.get("/api/leaderboard/avatars").get_json()
    assert data["elo_mode"] == "player" and data["avatars"] == []
