"""Tests for season avatar honours and the partner season-badges API."""

import sqlite3

import pytest

import webapp_config
from migrations.add_avatar_elo_mode import migrate


def _setup(elo_db, match_db):
    migrate(elo_db, match_db)


def _add_event(elo_db, event_id, name, mode="avatar", ended=True):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, end_date, is_active, elo_mode)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (event_id, name, "2026-08-01", "2026-09-30" if ended else None, 0 if ended else 1, mode),
    )
    conn.commit()
    conn.close()


def _add_entry(elo_db, event_id, user, avatar, elo, games):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO event_avatar_standings (event_id, user_id, avatar, user_display_name, event_elo, games_played)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (event_id, user[0], avatar, user[1], elo, games),
    )
    conn.commit()
    conn.close()


def _add_games(match_db, event_id, winner, w_avatar, loser, l_avatar, count, source=None):
    conn = sqlite3.connect(str(match_db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records_archive)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE match_records_archive ADD COLUMN source TEXT")
    for _ in range(count):
        conn.execute(
            "INSERT INTO match_records_archive (event_id, winner_id, winner_display_name, losser_id,"
            " losser_display_name, winner_avatar, loser_avatar, timestamp, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '2026-08-15 12:00:00', ?)",
            (event_id, winner[0], winner[1], loser[0], loser[1], w_avatar, l_avatar, source),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def patched(monkeypatch, elo_db, match_db, client):
    from services import avatar_honours

    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS match_records_archive (archive_id INTEGER PRIMARY KEY, event_id INTEGER,"
        " winner_id INTEGER, winner_display_name TEXT, losser_id INTEGER, losser_display_name TEXT, timestamp TEXT)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS active_pairings (id INTEGER)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(webapp_config, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", match_db)
    _setup(elo_db, match_db)
    avatar_honours.reset_cache()
    return client


A, B, C, D, E = (("1", "Ann"), ("2", "Ben"), ("3", "Cat"), ("4", "Dan"), ("5", "Eve"))


def test_top_three_per_avatar_by_ladder_elo(patched, elo_db, match_db):
    from services.avatar_honours import get_honours_by_player

    _add_event(elo_db, 9, "Gothic Season 9")
    _add_entry(elo_db, 9, A, "Imposter", 1700, 20)
    _add_entry(elo_db, 9, B, "Imposter", 1650, 12)
    _add_entry(elo_db, 9, E, "Imposter", 1800, 6)   # highest, but under 10 games
    _add_entry(elo_db, 9, C, "Imposter", 1600, 10)
    _add_entry(elo_db, 9, D, "Imposter", 1550, 30)  # fourth
    _add_games(match_db, 9, A, "Imposter", B, "Seer", 3)
    _add_games(match_db, 9, B, "Seer", A, "Imposter", 1)
    _add_games(match_db, 9, A, "Imposter", B, "Seer", 5, source="Bracket")  # not season games

    honours = get_honours_by_player()
    assert honours["1"][0]["title"] == "Gothic Season 9 Top Imposter"
    assert honours["1"][0]["elo"] == 1700
    assert (honours["1"][0]["wins"], honours["1"][0]["losses"]) == (3, 1)
    assert honours["2"][0]["label"] == "2nd Imposter"
    assert honours["3"][0]["label"] == "3rd Imposter"
    assert honours["3"][0]["wins"] is None  # no archived games found
    assert "4" not in honours
    assert "5" not in honours


def test_player_mode_and_running_seasons_earn_nothing(patched, elo_db, match_db):
    from services.avatar_honours import get_all_honours

    _add_event(elo_db, 7, "Gothic Season 7", mode="player")
    _add_event(elo_db, 10, "Season 10", ended=False)
    _add_entry(elo_db, 10, A, "Imposter", 1700, 20)
    assert get_all_honours() == []


def test_avatar_honours_route(patched, elo_db, match_db):
    _add_event(elo_db, 9, "Gothic Season 9")
    _add_entry(elo_db, 9, A, "Imposter", 1700, 20)
    _add_entry(elo_db, 9, B, "Druid", 1600, 11)
    data = patched.get("/api/avatar-honours").get_json()
    assert data["success"]
    assert data["honours"]["1"][0]["title"] == "Gothic Season 9 Top Imposter"
    assert data["honours"]["2"][0]["title"] == "Gothic Season 9 Top Druid"


class FakeBrackets:
    def __init__(self):
        self._repo = self

    def list_brackets(self, published_only=True):
        return [
            {"slug": "s7", "name": "Gothic Season 7 Postseason Bracket", "elo_event_name": None,
             "completed_at": "2026-10-01T00:00:00"},
        ]

    def get_player_marks(self):
        return {
            "1": {"entries": [{"slug": "s7", "name": "Gothic Season 7 Postseason Bracket",
                               "format": "constructed", "placement": 1, "label": "Champion",
                               "finish": "Champion"}]},
            "9": {"entries": [{"slug": "s7", "name": "Gothic Season 7 Postseason Bracket",
                               "format": "constructed", "placement": 17, "label": "Top cut",
                               "finish": "Top cut"}]},
        }


@pytest.fixture()
def partner(patched, monkeypatch):
    import routes.api.season_badges as season_badges

    monkeypatch.setattr(season_badges, "BracketService", FakeBrackets)
    monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "pso-key")
    return patched


def test_partner_badges_need_key(partner):
    assert partner.get("/api/partner/season-badges").status_code == 401


def test_partner_badges_combine_brackets_and_avatars(partner, elo_db, match_db):
    _add_event(elo_db, 7, "Gothic Season 7")
    _add_entry(elo_db, 7, A, "Imposter", 1700, 12)
    resp = partner.get("/api/partner/season-badges?user_id=1,9,404", headers={"X-API-Key": "pso-key"})
    assert resp.status_code == 200
    players = {p["user_id"]: p for p in resp.get_json()["players"]}

    assert players["1"]["brackets"][0]["title"] == "Gothic Season 7 Champion"
    assert players["1"]["brackets"][0]["season"] == "Gothic Season 7"
    assert players["1"]["avatar_honours"][0]["title"] == "Gothic Season 7 Top Imposter"
    assert players["9"]["brackets"][0]["label"] == "Top cut"
    assert players["9"]["avatar_honours"] == []
    assert players["404"] == {"user_id": "404", "brackets": [], "avatar_honours": []}


def test_partner_badges_without_user_id_lists_every_holder(partner, elo_db, match_db):
    _add_event(elo_db, 7, "Gothic Season 7")
    _add_entry(elo_db, 7, A, "Imposter", 1700, 12)
    _add_entry(elo_db, 7, B, "Druid", 1600, 12)
    data = partner.get("/api/partner/season-badges", headers={"X-API-Key": "pso-key"}).get_json()
    assert [p["user_id"] for p in data["players"]] == ["1", "2", "9"]


def test_bracket_season_names():
    from routes.api.season_badges import bracket_season

    assert bracket_season({"name": "Gothic Season 6 Postseason Bracket"}) == "Gothic Season 6"
    assert bracket_season({"name": "Season 8 Limited Top 8"}) == "Season 8"
    assert bracket_season({"name": "X", "elo_event_name": "Gothic Season 8"}) == "Gothic Season 8"


def test_player_counts_only_on_their_highest_ranked_avatar(patched, elo_db, match_db):
    from services.avatar_honours import get_honours_by_player

    _add_event(elo_db, 9, "Gothic Season 9")
    _add_entry(elo_db, 9, A, "Imposter", 1750, 20)   # Ann's best entry
    _add_entry(elo_db, 9, A, "Seer", 1700, 15)       # steps aside
    _add_entry(elo_db, 9, A, "Druid", 1800, 4)       # higher, but under 10 games
    _add_entry(elo_db, 9, B, "Seer", 1650, 12)
    _add_entry(elo_db, 9, C, "Seer", 1600, 12)
    _add_entry(elo_db, 9, D, "Seer", 1550, 12)

    honours = get_honours_by_player()
    assert [h["title"] for h in honours["1"]] == ["Gothic Season 9 Top Imposter"]
    assert honours["2"][0]["label"] == "Top Seer"
    assert honours["3"][0]["label"] == "2nd Seer"
    assert honours["4"][0]["label"] == "3rd Seer"


def test_season_top_avatars_needs_key(partner):
    assert partner.get("/api/partner/season-top-avatars").status_code == 401


def test_season_top_avatars_lists_each_past_season(partner, elo_db, match_db):
    _add_event(elo_db, 7, "Gothic Season 7")
    _add_entry(elo_db, 7, A, "Imposter", 1700, 12)
    _add_entry(elo_db, 7, B, "Imposter", 1650, 12)
    _add_entry(elo_db, 7, C, "Druid", 1600, 15)
    _add_event(elo_db, 6, "Gothic Season 6", mode="player")    # no avatar ladder
    _add_event(elo_db, 10, "Season 10", ended=False)            # still running
    _add_entry(elo_db, 10, D, "Imposter", 1900, 30)

    resp = partner.get("/api/partner/season-top-avatars", headers={"X-API-Key": "pso-key"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert [s["season"] for s in data["seasons"]] == ["Gothic Season 7"]
    tops = {a["avatar"]: a for a in data["seasons"][0]["avatars"]}
    assert set(tops) == {"Imposter", "Druid"}
    assert tops["Imposter"]["user_id"] == "1"
    assert tops["Imposter"]["name"] == "Ann"
    assert tops["Imposter"]["title"] == "Gothic Season 7 Top Imposter"
    assert tops["Druid"]["user_id"] == "3"

    deeper = partner.get("/api/partner/season-top-avatars?places=2",
                         headers={"X-API-Key": "pso-key"}).get_json()
    imposters = [a["user_id"] for a in deeper["seasons"][0]["avatars"] if a["avatar"] == "Imposter"]
    assert imposters == ["1", "2"]


def test_season_top_avatars_one_season_and_ladder_choice(partner, elo_db, match_db):
    _add_event(elo_db, 7, "Gothic Season 7")
    _add_entry(elo_db, 7, A, "Imposter", 1700, 12)
    _add_event(elo_db, 8, "Gothic Season 8")
    _add_entry(elo_db, 8, A, "Imposter", 1800, 20)   # Ann's best entry
    _add_entry(elo_db, 8, A, "Seer", 1750, 12)       # steps aside for honours
    _add_entry(elo_db, 8, B, "Seer", 1600, 12)
    key = {"X-API-Key": "pso-key"}

    by_name = partner.get("/api/partner/season-top-avatars?season=gothic season 8", headers=key).get_json()
    by_id = partner.get("/api/partner/season-top-avatars?season=8", headers=key).get_json()
    assert by_name == by_id
    seer = [a for a in by_id["seasons"][0]["avatars"] if a["avatar"] == "Seer"][0]
    assert seer["user_id"] == "2"   # same person as the season badge

    plain = partner.get("/api/partner/season-top-avatars?season=8&ladder=plain", headers=key).get_json()
    seer = [a for a in plain["seasons"][0]["avatars"] if a["avatar"] == "Seer"][0]
    assert seer["user_id"] == "1"   # raw ladder: Ann tops Seer too

    assert partner.get("/api/partner/season-top-avatars?season=99", headers=key).status_code == 404
    assert partner.get("/api/partner/season-top-avatars?places=4", headers=key).status_code == 400
    assert partner.get("/api/partner/season-top-avatars?ladder=x", headers=key).status_code == 400


def test_glicko2_season_wins_losses_come_from_season_table(patched, elo_db, match_db):
    """Season 9+ games stay in season_match_records (real layout), never archived."""
    from services import glicko2_season as g2
    from services.avatar_honours import get_honours_by_player

    conn = sqlite3.connect(str(match_db))
    g2.create_season_match_table(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(season_match_records)")}
    assert {"event_id", "winner_avatar", "loser_avatar", "source"} <= cols
    for i in range(4):
        winner, loser = (A, B) if i < 3 else (B, A)
        conn.execute(
            "INSERT INTO season_match_records (winner_id, winner_display_name, losser_id,"
            " losser_display_name, winner_avatar, loser_avatar, timestamp, source, event_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'Discord', 9)",
            (winner[0], winner[1], loser[0], loser[1],
             "Imposter" if winner == A else "Seer", "Seer" if winner == A else "Imposter",
             f"2027-01-02T10:0{i}:00"),
        )
    conn.commit()
    conn.close()
    _add_event(elo_db, 9, "Gothic Season 9")
    _add_entry(elo_db, 9, A, "Imposter", 1700, 12)

    honour = get_honours_by_player()["1"][0]
    assert (honour["wins"], honour["losses"]) == (3, 1)
