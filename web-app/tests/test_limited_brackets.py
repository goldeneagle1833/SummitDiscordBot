"""Tests for Limited season brackets: the Limited top 8 and its lifetime ELO."""

import json
import sqlite3

import pytest

import repositories.limited_repo as limited_repo
import services.brackets as brackets_module
import webapp_config
from repositories.brackets import BracketRepository
from services.brackets import BracketError, BracketService

PLAYERS = [str(100 + i) for i in range(1, 11)]  # Discord ids, seed order


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    """Point the Limited tables at temp databases."""
    elo_db = tmp_path / "elo.db"
    match_db = tmp_path / "match_records.db"
    monkeypatch.setattr(webapp_config, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", match_db)
    limited_repo.create_limited_tables()
    return elo_db, match_db


@pytest.fixture(autouse=True)
def events_dir(tmp_path, monkeypatch):
    import repositories.events as events_module

    path = tmp_path / "top-8-decks-by-event"
    path.mkdir()
    monkeypatch.setattr(events_module, "TOP_8_DIR", path)
    return path


def seed_limited_season(dbs, ended=True, live_games=True):
    """A Limited season: 10 players, P1 best. Optionally already archived."""
    elo_db, match_db = dbs
    conn = sqlite3.connect(str(elo_db))
    for i, user_id in enumerate(PLAYERS, start=1):
        conn.execute(
            "INSERT INTO limited_elo (user_id, user_display_name, elo, lifetime_elo) VALUES (?, ?, ?, ?)",
            (int(user_id), f"P{i}", 1700 - i * 10, 1500),
        )
    # Someone with no games this season is not on the ladder.
    conn.execute(
        "INSERT INTO limited_elo (user_id, user_display_name, elo, lifetime_elo) VALUES (999, 'Idle', 1800, 1600)"
    )
    conn.execute(
        "INSERT INTO limited_events (event_name, start_date, end_date, is_active) VALUES (?, ?, ?, ?)",
        ("Limited Season 3", "2026-09-01", "2026-10-01" if ended else None, 0 if ended else 1),
    )
    conn.commit()
    conn.close()

    if live_games:
        conn = sqlite3.connect(str(match_db))
        for user_id in PLAYERS:
            conn.execute(
                "INSERT INTO limited_match_records (winner_id, loser_id) VALUES (?, ?)",
                (int(user_id), 555),
            )
        conn.commit()
        conn.close()


class FakeNames:
    def get_display_names(self, ids):
        return {}

    def get_custom_display_names(self, ids):
        return {}

    def get_user_elo(self, user_id):
        return 1500


@pytest.fixture()
def repo(tmp_path, dbs):
    repository = BracketRepository(db_path=tmp_path / "brackets.db")
    repository.ensure_tables()
    return repository


@pytest.fixture()
def batches():
    return []


@pytest.fixture()
def service(repo, batches):
    names = FakeNames()
    return BracketService(
        repo=repo,
        elo_repo=names,
        profile_repo=names,
        pairing_notifier=batches.append,
    )


def lifetime(dbs, user_id):
    conn = sqlite3.connect(str(dbs[0]))
    row = conn.execute(
        "SELECT elo, lifetime_elo FROM limited_elo WHERE user_id = ?", (int(user_id),)
    ).fetchone()
    conn.close()
    return row


def archived_games(dbs):
    conn = sqlite3.connect(str(dbs[1]))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM limited_match_records_archive").fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return [dict(r) for r in rows]


def limited_bracket(service, size=8, publish=True):
    created = service.create_bracket(name="Limited Season 3 Top 8", size=size, source="limited")
    if publish:
        service.publish(created["bracket_id"])
    return created["slug"], created["bracket_id"]


class TestLimitedSeedPool:
    def test_the_pool_is_the_limited_season_ladder(self, service, dbs):
        seed_limited_season(dbs, ended=False)
        pool = service.get_seed_pool("limited")

        assert [p["user_id"] for p in pool["players"]] == PLAYERS
        assert pool["event"]["event_name"] == "Limited Season 3"
        assert pool["ticket_filter_applied"] is False

    def test_an_archived_season_seeds_from_its_final_standings(self, service, dbs):
        seed_limited_season(dbs, live_games=False)
        conn = sqlite3.connect(str(dbs[0]))
        limited_repo.create_limited_archive_tables()
        for rank, user_id in enumerate(PLAYERS[:3], start=1):
            conn.execute(
                "INSERT INTO limited_event_standings_archive (event_id, event_name, user_id,"
                " user_display_name, final_elo, final_rank) VALUES (1, 'Limited Season 3', ?, ?, ?, ?)",
                (int(user_id), f"P{rank}", 1700 - rank, rank),
            )
        conn.commit()
        conn.close()
        conn = sqlite3.connect(str(dbs[1]))
        for user_id in PLAYERS[:3]:
            conn.execute(
                "INSERT INTO limited_match_records_archive (event_id, winner_id, loser_id) VALUES (1, ?, 555)",
                (int(user_id),),
            )
        conn.commit()
        conn.close()

        pool = service.get_seed_pool("limited")
        assert [p["user_id"] for p in pool["players"]] == PLAYERS[:3]

    def test_seeding_from_it_makes_a_limited_bracket(self, service, repo, dbs):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service, publish=False)

        bracket = repo.get_bracket(bracket_id=bracket_id)
        assert bracket["format"] == "limited"
        assert [e["user_id"] for e in repo.get_entrants(bracket_id)] == PLAYERS[:8]

    def test_constructed_brackets_stay_constructed(self, service, repo, dbs):
        created = service.create_bracket(name="Manual", size=8, source="manual")
        assert repo.get_bracket(bracket_id=created["bracket_id"])["format"] == "constructed"

    def test_an_unknown_format_is_refused(self, service, dbs):
        with pytest.raises(BracketError, match="Unknown format"):
            service.create_bracket(name="X", size=8, source="manual", format="sealed")


class TestLimitedElo:
    def test_a_confirmed_result_moves_lifetime_limited_elo_only(self, service, repo, dbs):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service)
        match = repo.get_matches(bracket_id)[0]  # seed 1 v seed 8
        p1, p8 = match["p1_user_id"], match["p2_user_id"]
        season_before = lifetime(dbs, p1)[0], lifetime(dbs, p8)[0]

        service.report_result(slug, match["match_no"], p1, p1)
        service.confirm_result(slug, match["match_no"], p8, agree=True)

        assert lifetime(dbs, p1) == (season_before[0], 1516)
        assert lifetime(dbs, p8) == (season_before[1], 1484)
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["elo_applied_at"]
        assert (stored["winner_elo_change"], stored["loser_elo_change"]) == (16, -16)

    def test_the_game_goes_into_limited_history_for_that_season(self, service, repo, dbs):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], match["p1_user_id"], admin_id="a")

        (game,) = archived_games(dbs)
        assert game["event_id"] == 1
        assert str(game["winner_id"]) == match["p1_user_id"]
        assert game["winner_elo_change"] == 16
        assert game["match_comment"].startswith("Limited top cut game")

    def test_resetting_gives_the_points_back(self, service, repo, dbs):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service)
        match = repo.get_matches(bracket_id)[0]
        p1, p8 = match["p1_user_id"], match["p2_user_id"]

        service.set_result(slug, match["match_no"], p1, admin_id="a")
        service.reset_match(slug, match["match_no"])

        assert lifetime(dbs, p1)[1] == 1500
        assert lifetime(dbs, p8)[1] == 1500
        assert archived_games(dbs) == []

    def test_overturning_a_result_rates_it_the_other_way(self, service, repo, dbs):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service)
        match = repo.get_matches(bracket_id)[0]
        p1, p8 = match["p1_user_id"], match["p2_user_id"]

        service.set_result(slug, match["match_no"], p1, admin_id="a")
        service.set_result(slug, match["match_no"], p8, admin_id="a")

        assert lifetime(dbs, p1)[1] == 1484
        assert lifetime(dbs, p8)[1] == 1516
        assert len(archived_games(dbs)) == 1

    def test_the_startup_refund_leaves_limited_games_rated(self, service, repo, dbs):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], match["p1_user_id"], admin_id="a")

        assert service.refund_applied_elo() == 0
        assert service.archive_existing_records() == 0
        assert lifetime(dbs, match["p1_user_id"])[1] == 1516


class TestLimitedFinish:
    def _finish(self, service, repo, size=4):
        slug, bracket_id = limited_bracket(service, size=size)
        for round_no in (1, 2):
            for match in repo.get_matches(bracket_id):
                if match["round"] == round_no and match["state"] == "pending":
                    service.set_result(slug, match["match_no"], match["p1_user_id"], admin_id="a")
        return slug, bracket_id

    def test_finish_labels_say_limited(self):
        assert BracketService.finish_label(1, "limited") == "Limited Champion"
        assert BracketService.finish_label(3, "limited") == "Limited Top 4"
        assert BracketService.finish_label(20, "limited") == "Limited Top cut"
        assert BracketService.finish_label(1) == "Champion"

    def test_a_limited_title_is_its_own_mark(self, service, repo, dbs):
        seed_limited_season(dbs)
        self._finish(service, repo)

        marks = service.get_player_marks()[PLAYERS[0]]
        assert marks["limited_wins"] == 1
        assert marks["limited_best_label"] == "Limited Champion"
        # The constructed colour and yurts are untouched.
        assert marks["wins"] == 0
        assert marks["best_label"] is None
        assert marks["entries"][0]["label"] == "Limited Champion"
        assert marks["entries"][0]["finish"] == "Champion"
        assert marks["entries"][0]["format"] == "limited"

    def test_postseason_runs_carry_the_limited_label(self, service, repo, dbs):
        seed_limited_season(dbs)
        self._finish(service, repo)

        (run,) = service.get_player_postseason(PLAYERS[0])
        assert run["format"] == "limited"
        assert run["label"] == "Limited Champion"

    def test_a_finished_limited_bracket_stays_off_the_top8_page(self, service, repo, dbs, events_dir):
        seed_limited_season(dbs)
        slug, bracket_id = self._finish(service, repo)

        assert repo.get_bracket(bracket_id=bracket_id)["status"] == "complete"
        assert list(events_dir.iterdir()) == []
        with pytest.raises(BracketError, match="Limited brackets"):
            service.publish_to_top8(bracket_id)


class TestLimitedDecksAndTables:
    def test_a_draftsorcery_deck_can_be_submitted(self, service, repo, dbs, monkeypatch):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service)
        monkeypatch.setattr(
            brackets_module,
            "fetch_draftsorcery_deck",
            lambda url: {"avatar": [{"name": "Sorcerer", "quantity": 1}], "spellbook": [], "atlas": [], "sideboard": []},
        )

        result = service.submit_deck(slug, "https://draftsorcery.com/?deck=abc", actor_id=PLAYERS[0])

        assert result["avatar_name"] == "Sorcerer"
        deck = repo.get_deck(bracket_id, 1)
        assert deck["deck_url"] == "https://draftsorcery.com/?deck=abc"
        assert json.loads(deck["deck_json"])["avatar"][0]["name"] == "Sorcerer"

    def test_tables_open_as_limited_games(self, service, repo, dbs, monkeypatch):
        seed_limited_season(dbs)
        slug, bracket_id = limited_bracket(service)
        match = repo.get_matches(bracket_id)[0]
        for seed in (match["p1_seed"], match["p2_seed"]):
            repo.upsert_deck(bracket_id, seed, {
                "user_id": PLAYERS[seed - 1], "deck_url": f"https://draftsorcery.com/?deck={seed}",
                "deck_name": None, "avatar_name": None, "deck_json": "{}", "submitted_by": "a",
            })
        calls = []

        def fake_provision(pairing_id, players, queue_type="ranked"):
            calls.append(queue_type)
            return {"seats": {str(p["user_id"]): "https://playsorceryonline.com/x" for p in players}}

        monkeypatch.setattr(brackets_module, "provision_match_table", fake_provision)
        service.open_table(slug, match["match_no"], match["p1_user_id"])

        assert calls == ["limited"]

    def test_pairings_say_they_are_limited(self, service, dbs, batches):
        seed_limited_season(dbs)
        limited_bracket(service)

        assert batches[0]["format"] == "limited"
        assert all(p["format"] == "limited" for p in batches[0]["pairings"])
