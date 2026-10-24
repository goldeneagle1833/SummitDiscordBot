"""Community brackets: ones approved players (the Bracket Organizer role) run."""

import sqlite3

import pytest

import repositories.limited_repo as limited_repo
import webapp_config
from repositories.brackets import BracketRepository
from services.brackets import COMMUNITY_MAX_OPEN, BracketError, BracketService

ORGANIZER_ROLE = "777"
PLAYERS = [str(200 + i) for i in range(1, 9)]


class FakeNames:
    def get_display_names(self, ids):
        return {}

    def get_custom_display_names(self, ids):
        return {}

    def get_user_elo(self, user_id):
        return 1500


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
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
        repo=repo, elo_repo=names, profile_repo=names, pairing_notifier=batches.append
    )


def community_bracket(service, format="limited", organizer="900", players=PLAYERS):
    created = service.create_bracket(
        name="Friday Draft", size=8, source="manual", created_by=organizer,
        format=format, kind="community",
    )
    service.set_entrants(
        created["bracket_id"],
        [{"user_id": p, "display_name": f"P{i}"} for i, p in enumerate(players, start=1)],
    )
    service.publish(created["bracket_id"])
    return created["slug"], created["bracket_id"]


def play_first_match(service, repo, slug, bracket_id):
    match = repo.get_matches(bracket_id)[0]
    winner, loser = match["p1_user_id"], match["p2_user_id"]
    service.report_result(slug, match["match_no"], winner, winner)
    service.confirm_result(slug, match["match_no"], loser, agree=True)
    return match, winner, loser


def lifetime(dbs, user_id):
    conn = sqlite3.connect(str(dbs[0]))
    row = conn.execute(
        "SELECT elo, lifetime_elo FROM limited_elo WHERE user_id = ?", (int(user_id),)
    ).fetchone()
    conn.close()
    return row


class TestCreating:
    def test_a_community_bracket_starts_empty_whatever_it_asks_for(self, service, repo):
        created = service.create_bracket(
            name="Store Night", size=8, source="ticket_holders", created_by="900",
            set_name="Gothic", kind="community",
        )
        bracket = repo.get_bracket(bracket_id=created["bracket_id"])
        assert bracket["kind"] == "community"
        assert bracket["seeded_from"] == "manual"
        assert bracket["set_name"] is None
        assert repo.get_entrants(created["bracket_id"]) == []

    def test_brackets_are_official_unless_said_otherwise(self, service, repo):
        created = service.create_bracket(name="Top Cut", size=8, source="manual")
        assert repo.get_bracket(bracket_id=created["bracket_id"])["kind"] == "official"

    def test_an_organizer_has_only_so_many_unfinished_brackets(self, service):
        for i in range(COMMUNITY_MAX_OPEN):
            service.create_bracket(name=f"B{i}", size=4, source="manual", created_by="900", kind="community")
        with pytest.raises(BracketError, match="aren't finished"):
            service.create_bracket(name="One more", size=4, source="manual", created_by="900", kind="community")
        # Someone else is unaffected.
        service.create_bracket(name="Theirs", size=4, source="manual", created_by="901", kind="community")

    def test_an_organizer_sees_only_their_own(self, service):
        service.create_bracket(name="Mine", size=4, source="manual", created_by="900", kind="community")
        service.create_bracket(name="Theirs", size=4, source="manual", created_by="901", kind="community")
        service.create_bracket(name="Top Cut", size=4, source="manual", created_by="900")
        names = [b["name"] for b in service.list_brackets(include_drafts=True, organizer_id="900")]
        assert names == ["Mine"]


class TestLimitedElo:
    def test_a_result_moves_lifetime_limited_elo_and_no_season(self, service, repo, dbs):
        slug, bracket_id = community_bracket(service)
        match, winner, loser = play_first_match(service, repo, slug, bracket_id)

        assert lifetime(dbs, winner) == (1500, 1516)
        assert lifetime(dbs, loser) == (1500, 1484)
        conn = sqlite3.connect(str(dbs[1]))
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM limited_match_records_archive")]
        live = conn.execute("SELECT COUNT(*) FROM limited_match_records").fetchone()[0]
        conn.close()
        assert live == 0  # Never on the running season's ladder
        assert len(rows) == 1
        assert rows[0]["event_id"] == 0
        assert rows[0]["match_comment"].startswith("Limited bracket game - Friday Draft")

    def test_deleting_the_bracket_gives_the_points_back(self, service, repo, dbs):
        slug, bracket_id = community_bracket(service)
        _, winner, loser = play_first_match(service, repo, slug, bracket_id)

        service.delete_bracket(bracket_id)
        assert lifetime(dbs, winner)[1] == 1500
        assert lifetime(dbs, loser)[1] == 1500

    def test_unpublishing_gives_the_points_back(self, service, repo, dbs):
        slug, bracket_id = community_bracket(service)
        _, winner, _ = play_first_match(service, repo, slug, bracket_id)

        service.unpublish(bracket_id)
        assert lifetime(dbs, winner)[1] == 1500


class TestConstructed:
    def test_a_result_stays_on_the_bracket_page(self, service, repo, dbs):
        slug, bracket_id = community_bracket(service, format="constructed")
        match, _, _ = play_first_match(service, repo, slug, bracket_id)

        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["state"] == "complete"
        assert stored["match_record_id"] is None


class TestHonours:
    def finish(self, service, repo, slug, bracket_id):
        while True:
            open_matches = [
                m for m in repo.get_matches(bracket_id)
                if m["state"] == "pending" and m["p1_user_id"] and m["p2_user_id"]
            ]
            if not open_matches:
                break
            m = open_matches[0]
            service.set_result(slug, m["match_no"], m["p1_user_id"], "admin")

    def test_community_finishes_are_not_summit_honours(self, service, repo, dbs, events_dir):
        slug, bracket_id = community_bracket(service, format="constructed")
        self.finish(service, repo, slug, bracket_id)

        assert repo.get_bracket(bracket_id=bracket_id)["status"] == "complete"
        assert service.get_player_marks() == {}
        assert service.get_player_postseason(PLAYERS[0]) == []
        assert list(events_dir.iterdir()) == []
        with pytest.raises(BracketError, match="Community brackets"):
            service.publish_to_top8(bracket_id)


class TestPairings:
    def test_pairings_say_they_are_community(self, service, batches):
        community_bracket(service)
        assert batches and batches[0]["community"] is True
        assert all(p["community"] for p in batches[0]["pairings"])


# -- API ------------------------------------------------------------


@pytest.fixture()
def organizer_role(monkeypatch):
    import services.brackets as brackets_module

    monkeypatch.setattr(webapp_config, "BRACKET_ORGANIZER_ROLE_IDS", {ORGANIZER_ROLE})
    monkeypatch.setattr(webapp_config, "DISCORD_BOT_TOKEN", "")
    # Publishing would hand pairings to the bot on a background thread.
    monkeypatch.setattr(brackets_module, "_send_pairing_to_bot", lambda payload: None)
    yield
    # These requests leave per-endpoint metrics buffered in the process-wide
    # collector; drop them so they don't crowd later monitoring tests.
    from utils.monitoring import collector

    with collector._lock:
        collector._requests.clear()


def login(client, user_id, roles=()):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = f"user{user_id}"
        sess["auth_provider"] = "discord"
        sess["discord_roles"] = list(roles)


class TestApi:
    def create(self, client, **body):
        return client.post(
            "/api/admin/brackets", json={"name": "Friday Draft", "format": "limited", **body}
        )

    def fill_and_publish(self, client, slug, players):
        client.put(
            f"/api/admin/brackets/{slug}/entrants",
            json={"entrants": [{"user_id": p, "display_name": p} for p in players]},
        )
        return client.post(f"/api/admin/brackets/{slug}/publish")

    def test_players_without_the_role_cannot_create(self, client, organizer_role):
        login(client, "301")
        assert self.create(client).status_code == 403
        assert client.get("/api/admin/brackets").status_code == 403

    def test_an_organizer_makes_a_community_bracket(self, client, organizer_role):
        login(client, "300", [ORGANIZER_ROLE])
        resp = self.create(client, kind="official", source="ticket_holders")
        assert resp.status_code == 201
        slug = resp.get_json()["slug"]

        listed = client.get("/api/admin/brackets").get_json()["brackets"]
        assert [(b["slug"], b["kind"], b["format"]) for b in listed] == [(slug, "community", "limited")]
        assert client.get("/api/me").get_json()["is_bracket_organizer"] is True

    def test_an_organizer_runs_their_own_bracket(self, client, organizer_role):
        login(client, "300", [ORGANIZER_ROLE])
        slug = self.create(client).get_json()["slug"]
        assert self.fill_and_publish(client, slug, ["311", "312", "313", "314"]).status_code == 200

        detail = client.get(f"/api/brackets/{slug}").get_json()
        assert detail["viewer_can_manage"] is True
        assert detail["bracket"]["kind"] == "community"
        first = detail["rounds"][0]["matches"][0]
        resp = client.post(
            f"/api/admin/brackets/{slug}/matches/{first['match_no']}/result",
            json={"winner_user_id": first["p1_user_id"]},
        )
        assert resp.status_code == 200

    def test_an_organizer_cannot_settle_their_own_match(self, client, organizer_role):
        login(client, "300", [ORGANIZER_ROLE])
        slug = self.create(client).get_json()["slug"]
        self.fill_and_publish(client, slug, ["300", "312"])
        resp = client.post(
            f"/api/admin/brackets/{slug}/matches/1/result", json={"winner_user_id": "300"}
        )
        assert resp.status_code == 403
        assert client.post(f"/api/admin/brackets/{slug}/matches/1/reset").status_code == 403

    def test_nobody_else_can_manage_it(self, client, organizer_role):
        login(client, "300", [ORGANIZER_ROLE])
        slug = self.create(client).get_json()["slug"]

        login(client, "400", [ORGANIZER_ROLE])
        assert client.get(f"/api/admin/brackets/{slug}").status_code == 403
        assert client.delete(f"/api/admin/brackets/{slug}").status_code == 403
        assert client.get(f"/api/brackets/{slug}").status_code == 404  # Still a draft

        # Losing the role takes the bracket away too.
        login(client, "300")
        assert client.post(f"/api/admin/brackets/{slug}/publish").status_code == 403

    def test_organizers_cannot_touch_official_brackets(self, client, admin_session, organizer_role):
        created = admin_session.post(
            "/api/admin/brackets", json={"name": "Top Cut", "size": 2, "source": "manual"}
        ).get_json()
        login(client, "300", [ORGANIZER_ROLE])
        assert client.get(f"/api/admin/brackets/{created['slug']}").status_code == 403

    def test_admins_still_see_and_run_everything(self, client, admin_session, organizer_role):
        admin_session.post("/api/admin/brackets", json={"name": "Top Cut", "size": 2, "source": "manual"})
        login(client, "300", [ORGANIZER_ROLE])
        slug = self.create(client).get_json()["slug"]

        login(client, "admin_user_1")
        names = {b["name"] for b in client.get("/api/admin/brackets").get_json()["brackets"]}
        assert names == {"Top Cut", "Friday Draft"}
        assert client.get(f"/api/admin/brackets/{slug}").status_code == 200

    def test_organizers_search_players_by_name(self, client, organizer_role):
        login(client, "300", [ORGANIZER_ROLE])
        resp = client.get("/api/brackets/organizer/search-players?q=ab")
        assert resp.status_code == 200
        assert resp.get_json()["users"] == []
        login(client, "301")
        assert client.get("/api/brackets/organizer/search-players?q=ab").status_code == 403
