"""Tests for season avatar honours and the partner season-badges API."""

import json
import sqlite3

import pytest

import webapp_config


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar}]})


def _ensure_archive(db):
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE IF NOT EXISTS match_records_archive AS SELECT * FROM match_records WHERE 0")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records_archive)")}
    if "event_id" not in cols:
        conn.execute("ALTER TABLE match_records_archive ADD COLUMN event_id INTEGER")
    conn.commit()
    conn.close()


def _add_games(db, winner, loser, w_avatar, l_avatar, count, event_id=None):
    """Archived games under event_id, or live games when event_id is None."""
    _ensure_archive(db)
    table = "match_records" if event_id is None else "match_records_archive"
    conn = sqlite3.connect(str(db))
    for _ in range(count):
        cols = ["winner_id", "winner_display_name", "losser_id", "losser_display_name",
                "json_deck_data_winner", "json_deck_data_loser", "timestamp", "source"]
        vals = [winner[0], winner[1], loser[0], loser[1], _deck(w_avatar), _deck(l_avatar),
                "2026-09-01 12:00:00", "Discord"]
        if event_id is not None:
            cols.append("event_id")
            vals.append(event_id)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals
        )
    conn.commit()
    conn.close()


def _add_event(elo_db, event_id, name, ended=True):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, end_date, is_active) VALUES (?, ?, ?, ?, ?)",
        (event_id, name, "2026-08-01", "2026-09-30" if ended else None, 0 if ended else 1),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def patched(monkeypatch, elo_db, match_db, client):
    import routes.api.avatars as avatars
    from services import avatar_honours

    monkeypatch.setattr(avatars, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(avatars, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(avatars, "SEASON_FILTERS", [])
    avatars.reset_rows_cache()
    avatar_honours.reset_cache()
    return client


A, B, C, D, E = (("1", "Ann"), ("2", "Ben"), ("3", "Cat"), ("4", "Dan"), ("5", "Eve"))


def test_top_three_per_avatar_for_ended_season(patched, elo_db, match_db):
    from services.avatar_honours import get_honours_by_player

    _add_event(elo_db, 7, "Gothic Season 7")
    _add_games(match_db, A, E, "Imposter", "Druid", 14, event_id=7)  # 14-0
    _add_games(match_db, B, E, "Imposter", "Druid", 12, event_id=7)  # 12-0
    _add_games(match_db, C, E, "Imposter", "Druid", 10, event_id=7)  # 10-0
    _add_games(match_db, D, E, "Imposter", "Druid", 11, event_id=7)  # 11-0 beats Cat
    _add_games(match_db, E, A, "Imposter", "Druid", 3, event_id=7)   # Eve: under 10 games

    honours = get_honours_by_player()
    assert honours["1"][0]["title"] == "Gothic Season 7 Top Imposter"
    assert honours["2"][0]["label"] == "2nd Imposter"
    assert honours["4"][0]["label"] == "3rd Imposter"
    assert "3" not in honours  # fourth
    # Eve went 0-47 on Druid: 47 games, ranked third or better on Druid only
    assert all(h["avatar"] == "Druid" for h in honours["5"])


def test_running_season_earns_nothing(patched, elo_db, match_db):
    from services.avatar_honours import get_all_honours

    _add_event(elo_db, 9, "Season 9", ended=False)
    _add_games(match_db, A, B, "Imposter", "Druid", 15)
    assert get_all_honours() == []


def test_avatar_honours_route(patched, elo_db, match_db):
    _add_event(elo_db, 7, "Gothic Season 7")
    _add_games(match_db, A, B, "Imposter", "Druid", 12, event_id=7)
    data = patched.get("/api/avatar-honours").get_json()
    assert data["success"]
    assert data["honours"]["1"][0]["title"] == "Gothic Season 7 Top Imposter"
    assert data["honours"]["2"][0]["title"] == "Gothic Season 7 Top Druid"


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
    _add_games(match_db, A, B, "Imposter", "Druid", 12, event_id=7)
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
    _add_games(match_db, A, B, "Imposter", "Druid", 12, event_id=7)
    data = partner.get("/api/partner/season-badges", headers={"X-API-Key": "pso-key"}).get_json()
    assert [p["user_id"] for p in data["players"]] == ["1", "2", "9"]


def test_bracket_season_names():
    from routes.api.season_badges import bracket_season

    assert bracket_season({"name": "Gothic Season 6 Postseason Bracket"}) == "Gothic Season 6"
    assert bracket_season({"name": "Season 8 Limited Top 8"}) == "Season 8"
    assert bracket_season({"name": "X", "elo_event_name": "Gothic Season 8"}) == "Gothic Season 8"
