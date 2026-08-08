"""Regression tests for avatar-aware admin maintenance."""

import datetime
import sqlite3

from repositories import matches as matches_module
from services import admin as admin_module
from services import paper_elo
from services import seasons as seasons_module
from services.admin import AdminService
from services.seasons import SeasonsService


class FakeEloRepository:
    def __init__(self):
        self.ratings = {1: 1600, 2: 1400}
        self.upserts = []

    def get_user_elo(self, user_id):
        return self.ratings.get(int(user_id))

    def upsert_user_elo(self, user_id, display_name, new_elo):
        self.ratings[int(user_id)] = new_elo
        self.upserts.append((int(user_id), display_name, new_elo))


class FakeMatchRepository:
    def get_match_full_details(self, match_id):
        return {
            "match_id": match_id,
            "winner_id": 1,
            "loser_id": 2,
            "winner_name": "Alice",
            "loser_name": "Bob",
            "winner_elo_change": 8,
            "loser_elo_change": -8,
            "winner_lifetime_elo_change": 16,
            "loser_lifetime_elo_change": -15,
            "winner_avatar": "Impostor",
            "loser_avatar": "Battlemage",
            "match_type": "ranked",
            "timestamp": "2026-01-01T12:00:00",
        }

    def delete_match(self, match_id):
        return match_id == 42


def test_web_admin_bot_removal_uses_lifetime_delta_and_replays_avatar_ladder(
    monkeypatch,
):
    replayed = []
    monkeypatch.setattr(
        admin_module,
        "recalculate_avatar_event_for_timestamp",
        lambda source, timestamp: replayed.append((source, timestamp)),
    )
    elo_repo = FakeEloRepository()
    service = AdminService(elo_repo=elo_repo, match_repo=FakeMatchRepository())

    result = service._remove_bot_match("42")

    assert result["success"] is True
    assert elo_repo.ratings == {1: 1584, 2: 1415}
    assert replayed == [("online", "2026-01-01T12:00:00")]


class FakeSeasonsRepository:
    def get_season_by_id(self, season_id):
        return {
            "season_id": season_id,
            "creator_id": "9",
            "status": "active",
            "end_date": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
        }

    def get_season_members(self, _season_id):
        return [
            {"user_id": "1", "display_name": "Alice"},
            {"user_id": "2", "display_name": "Bob"},
        ]


def test_custom_season_report_persists_required_avatar_and_lifetime_fields(
    tmp_path, monkeypatch
):
    match_path = tmp_path / "matches.db"
    conn = sqlite3.connect(match_path)
    conn.execute("""CREATE TABLE match_reports_web (
        match_id TEXT PRIMARY KEY, reporter_id TEXT, winner_id TEXT,
        winner_display_name TEXT, losser_id TEXT, losser_display_name TEXT,
        did_win INTEGER, timestamp TEXT, first_player TEXT, match_time INTEGER,
        curiosa_url TEXT, curiosa_url_winner TEXT, curiosa_url_loser TEXT,
        match_comment TEXT, json_deck_data TEXT, json_deck_data_winner TEXT,
        json_deck_data_loser TEXT, winner_elo_change INTEGER,
        loser_elo_change INTEGER, winner_went_first TEXT,
        loser_went_first TEXT, source TEXT, match_type TEXT, season_id INTEGER,
        winner_lifetime_elo_after INTEGER, loser_lifetime_elo_after INTEGER,
        winner_lifetime_elo_change INTEGER, loser_lifetime_elo_change INTEGER,
        winner_avatar TEXT, loser_avatar TEXT
    )""")
    conn.commit()
    conn.close()

    monkeypatch.setattr(seasons_module, "MATCH_RECORDS_DB_PATH", match_path)
    monkeypatch.setattr(matches_module, "MATCH_RECORDS_DB_PATH", match_path)
    matches_module.MatchRepository._columns_ensured = False
    monkeypatch.setattr(
        matches_module.MatchRepository,
        "get_last_opponent",
        lambda self, user_id: None,
    )
    monkeypatch.setattr(
        paper_elo,
        "update_paper_match_elos",
        lambda *args, **kwargs: (
            (1516, 16, 1508, 8, True),
            (1484, -16, 1492, -8, True),
        ),
    )

    service = object.__new__(SeasonsService)
    service.repo = FakeSeasonsRepository()
    service.update_season_elos = lambda *args, **kwargs: []

    result = service.report_match_as_creator(
        "9", 3, "1", "2", winner_avatar="Impostor", loser_avatar="Battlemage"
    )

    assert result["match_id"] == "web_1"
    conn = sqlite3.connect(match_path)
    stored = conn.execute(
        """SELECT winner_avatar, loser_avatar,
                  winner_lifetime_elo_change, loser_lifetime_elo_change
           FROM match_reports_web"""
    ).fetchone()
    conn.close()
    assert stored == ("Impostor", "Battlemage", 16, -16)
