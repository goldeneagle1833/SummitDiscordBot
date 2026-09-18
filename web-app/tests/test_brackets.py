"""Tests for bracket seeding, publishing, and player-reported results."""

import time

import pytest

from repositories.brackets import BracketRepository
from services.bracket_builder import (
    bracket_size_for,
    build_matches,
    champion,
    round_title,
    seed_order,
)
from services.brackets import BracketError, BracketService, slugify
from tests.conftest import seed_elo_data, seed_matches


def make_entrants(count):
    return [
        {"user_id": f"u{i}", "display_name": f"P{i}", "elo": 2000 - i}
        for i in range(1, count + 1)
    ]


@pytest.fixture()
def repo(tmp_path):
    repository = BracketRepository(db_path=tmp_path / "brackets.db")
    repository.ensure_tables()
    return repository


class FakeLeaderboard:
    """Stands in for LeaderboardService so seeding tests stay focused."""

    def __init__(self, players=None, event=None):
        self._players = players if players is not None else [
            {"id": f"u{i}", "name": f"P{i}", "event_elo": 2000 - i, "wins": 5, "losses": 2}
            for i in range(1, 21)
        ]
        self._event = event or {"event_id": 7, "event_name": "Season 7"}

    def get_event_leaderboard(self):
        return {"event": self._event, "leaderboard": self._players}

    def get_leaderboard(self):
        return self._players


@pytest.fixture()
def service(repo):
    return BracketService(repo=repo, leaderboard_service=FakeLeaderboard())


def published(service, repo, count=8, name="Test Cup"):
    """Create and publish a bracket of `count` seeded players."""
    created = service.create_bracket(name=name, size=count, source="overall")
    service.publish(created["bracket_id"])
    return created["slug"], created["bracket_id"]


# -- Bracket maths ------------------------------------------------


class TestSeeding:
    def test_bracket_size_rounds_up_to_a_power_of_two(self):
        assert bracket_size_for(2) == 2
        assert bracket_size_for(8) == 8
        assert bracket_size_for(13) == 16
        assert bracket_size_for(17) == 32

    def test_a_bracket_needs_two_players(self):
        with pytest.raises(ValueError):
            bracket_size_for(1)

    def test_seed_order_keeps_the_top_seeds_apart(self):
        assert seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
        order = seed_order(16)
        # Seeds 1 and 2 sit in opposite halves, so they can only meet in the final.
        assert order.index(1) < 8 <= order.index(2)

    def test_seed_order_rejects_odd_sizes(self):
        with pytest.raises(ValueError):
            seed_order(12)

    def test_round_titles(self):
        assert round_title(4, 4) == "Finals"
        assert round_title(3, 4) == "Semifinals"
        assert round_title(2, 4) == "Quarterfinals"
        assert round_title(1, 4) == "Round 1"


class TestBuildMatches:
    def test_full_bracket_has_no_byes(self):
        matches = build_matches(make_entrants(8))
        assert len([m for m in matches if m["state"] == "bye"]) == 0
        assert len(matches) == 7
        assert matches[0]["p1_name"] == "P1"
        assert matches[0]["p2_name"] == "P8"

    def test_top_seeds_get_the_byes(self):
        matches = build_matches(make_entrants(13))
        byes = [m["p1_name"] or m["p2_name"] for m in matches if m["state"] == "bye"]
        assert sorted(byes) == ["P1", "P2", "P3"]

    def test_a_slot_waiting_on_a_match_is_not_a_bye(self):
        """The seed-1 quarterfinal waits on a real match; it must stay pending."""
        matches = build_matches(make_entrants(13))
        quarter = next(m for m in matches if m["round"] == 2 and m["position"] == 1)
        assert quarter["p1_name"] == "P1"
        assert quarter["p2_name"] is None
        assert quarter["state"] == "pending"

    def test_no_branch_is_left_empty(self):
        """The bracket is the next power of two up, so byes never fill a whole branch."""
        for count in (3, 5, 9, 13, 17):
            matches = build_matches(make_entrants(count))
            assert not [m for m in matches if m["state"] == "empty"]
            first_round = [m for m in matches if m["round"] == 1]
            assert all(m["p1_seed"] or m["p2_seed"] for m in first_round)

    def test_byes_cascade_into_the_next_round(self):
        matches = build_matches(make_entrants(5))
        semi = next(m for m in matches if m["round"] == 2 and m["position"] == 2)
        assert {semi["p1_name"], semi["p2_name"]} == {"P2", "P3"}

    def test_two_player_bracket_is_a_single_final(self):
        matches = build_matches(make_entrants(2))
        assert len(matches) == 1
        assert matches[0]["round_title"] == "Finals"

    def test_winners_point_at_the_right_next_slot(self):
        matches = build_matches(make_entrants(8))
        first, second = matches[0], matches[1]
        assert first["next_match_no"] == second["next_match_no"]
        assert {first["next_slot"], second["next_slot"]} == {1, 2}

    def test_no_champion_until_the_final_is_decided(self):
        assert champion(build_matches(make_entrants(8))) is None


# -- Seeding a bracket from the ladder ----------------------------


class TestSeedPool:
    def test_slugify(self):
        assert slugify("Summit Gothic Season 1!") == "summit-gothic-season-1"
        assert slugify("") == "bracket"

    def test_pool_without_a_ticket_roster_returns_everyone(self, service):
        pool = service.get_seed_pool("ticket_holders")
        assert len(pool["players"]) == 20
        # Nothing was filtered, and the caller is told so.
        assert pool["ticket_filter_applied"] is False

    def test_pool_filters_to_ticket_holders_once_synced(self, service, repo):
        repo.replace_ticket_holders([{"user_id": "u3"}, {"user_id": "u5"}])
        pool = service.get_seed_pool("ticket_holders")
        assert [p["display_name"] for p in pool["players"]] == ["P3", "P5"]
        assert pool["ticket_filter_applied"] is True
        assert all(p["is_ticket_holder"] for p in pool["players"])

    def test_overall_source_ignores_the_ticket_filter(self, service, repo):
        repo.replace_ticket_holders([{"user_id": "u3"}])
        pool = service.get_seed_pool("overall")
        assert len(pool["players"]) == 20
        assert next(p for p in pool["players"] if p["user_id"] == "u3")["is_ticket_holder"]


class TestCreateBracket:
    def test_creates_a_draft_seeded_from_the_ladder(self, service, repo):
        created = service.create_bracket(name="Season 7 Playoff", size=8, source="overall")
        bracket = repo.get_bracket(bracket_id=created["bracket_id"])

        assert bracket["status"] == "draft"
        assert bracket["slug"] == "season-7-playoff"
        assert bracket["elo_event_name"] == "Season 7"
        entrants = repo.get_entrants(created["bracket_id"])
        assert [e["display_name"] for e in entrants] == [f"P{i}" for i in range(1, 9)]
        assert entrants[0]["seed"] == 1

    def test_any_starting_count_is_allowed(self, service, repo):
        created = service.create_bracket(name="Odd Cup", size=13, source="overall")
        assert created["entrant_count"] == 13
        assert repo.get_bracket(bracket_id=created["bracket_id"])["bracket_size"] == 16

    def test_reports_when_the_pool_is_too_small(self, repo):
        service = BracketService(repo=repo, leaderboard_service=FakeLeaderboard(players=[
            {"id": "u1", "name": "P1", "event_elo": 1900, "wins": 1, "losses": 0},
            {"id": "u2", "name": "P2", "event_elo": 1800, "wins": 1, "losses": 0},
        ]))
        created = service.create_bracket(name="Small", size=16, source="overall")
        assert created["entrant_count"] == 2
        assert created["short_by"] == 14

    def test_manual_source_starts_empty(self, service):
        created = service.create_bracket(name="Manual", size=8, source="manual")
        assert created["entrant_count"] == 0

    def test_slugs_do_not_collide(self, service):
        first = service.create_bracket(name="Cup", size=4, source="overall")
        second = service.create_bracket(name="Cup", size=4, source="overall")
        assert first["slug"] == "cup"
        assert second["slug"] == "cup-2"

    @pytest.mark.parametrize("size", [0, 1, 500])
    def test_rejects_silly_sizes(self, service, size):
        with pytest.raises(BracketError):
            service.create_bracket(name="Bad", size=size, source="overall")

    def test_rejects_a_missing_name(self, service):
        with pytest.raises(BracketError):
            service.create_bracket(name="   ", size=8, source="overall")


class TestSeedEditing:
    def test_move_an_entrant_and_shift_the_rest(self, service, repo):
        created = service.create_bracket(name="Cup", size=4, source="overall")
        service.move_entrant(created["bracket_id"], 4, 1)
        assert [e["display_name"] for e in repo.get_entrants(created["bracket_id"])] == [
            "P4", "P1", "P2", "P3",
        ]

    def test_move_rejects_out_of_range_seeds(self, service):
        created = service.create_bracket(name="Cup", size=4, source="overall")
        with pytest.raises(BracketError):
            service.move_entrant(created["bracket_id"], 1, 9)

    def test_shuffle_keeps_the_same_field(self, service, repo):
        created = service.create_bracket(name="Cup", size=8, source="overall")
        service.shuffle_seeds(created["bracket_id"])
        entrants = repo.get_entrants(created["bracket_id"])
        assert sorted(e["display_name"] for e in entrants) == sorted(f"P{i}" for i in range(1, 9))
        assert [e["seed"] for e in entrants] == list(range(1, 9))

    def test_set_entrants_drops_blanks_and_duplicate_accounts(self, service, repo):
        created = service.create_bracket(name="Cup", size=2, source="overall")
        service.set_entrants(created["bracket_id"], [
            {"user_id": "u1", "display_name": "P1"},
            {"user_id": "u1", "display_name": "P1 again"},
            {"display_name": "   "},
            {"display_name": "Guest with no account"},
        ])
        entrants = repo.get_entrants(created["bracket_id"])
        assert [e["display_name"] for e in entrants] == ["P1", "Guest with no account"]

    def test_seeding_is_locked_once_published(self, service, repo):
        slug, bracket_id = published(service, repo, 4)
        with pytest.raises(BracketError, match="draft"):
            service.shuffle_seeds(bracket_id)

    def test_unpublish_returns_a_bracket_to_draft(self, service, repo):
        slug, bracket_id = published(service, repo, 4)
        service.unpublish(bracket_id)
        assert repo.get_bracket(bracket_id=bracket_id)["status"] == "draft"
        assert repo.get_matches(bracket_id) == []
        service.shuffle_seeds(bracket_id)


class TestPublishing:
    def test_publish_generates_the_tree(self, service, repo):
        created = service.create_bracket(name="Cup", size=13, source="overall")
        result = service.publish(created["bracket_id"])

        assert result["bracket_size"] == 16
        assert result["byes"] == 3
        assert repo.get_bracket(bracket_id=created["bracket_id"])["status"] == "published"
        assert repo.get_bracket(bracket_id=created["bracket_id"])["published_at"]

    def test_cannot_publish_an_empty_field(self, service):
        created = service.create_bracket(name="Manual", size=8, source="manual")
        with pytest.raises(BracketError, match="at least 2"):
            service.publish(created["bracket_id"])

    def test_drafts_are_hidden_from_the_public(self, service):
        created = service.create_bracket(name="Cup", size=4, source="overall")
        assert service.get_bracket_detail("cup") is None
        assert service.get_bracket_detail("cup", include_drafts=True) is not None
        assert service.list_brackets() == []
        assert len(service.list_brackets(include_drafts=True)) == 1


# -- Reporting ----------------------------------------------------


class TestReporting:
    def _first_match(self, service, slug):
        detail = service.get_bracket_detail(slug)
        return detail["rounds"][0]["matches"][0]

    def test_a_player_reports_and_the_opponent_confirms(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)  # P1 vs P8

        result = service.report_result(slug, match["match_no"], "u1", "u1")
        assert result["state"] == "reported"
        assert result["awaiting"] == "P8"
        assert repo.get_match(bracket_id, match["match_no"])["state"] == "reported"

        service.confirm_result(slug, match["match_no"], "u8", agree=True)
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["state"] == "complete"
        assert stored["winner_user_id"] == "u1"

    def test_the_winner_moves_into_the_next_round(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)

        service.report_result(slug, match["match_no"], "u1", "u1")
        service.confirm_result(slug, match["match_no"], "u8", agree=True)

        parent = repo.get_match(bracket_id, match["next_match_no"])
        assert parent[f"p{match['next_slot']}_user_id"] == "u1"
        assert parent[f"p{match['next_slot']}_name"] == "P1"

    def test_only_the_two_players_can_report(self, service, repo):
        slug, _ = published(service, repo, 8)
        match = self._first_match(service, slug)
        with pytest.raises(BracketError, match="Only the two players"):
            service.report_result(slug, match["match_no"], "u5", "u1")

    def test_the_winner_has_to_be_in_the_match(self, service, repo):
        slug, _ = published(service, repo, 8)
        match = self._first_match(service, slug)
        with pytest.raises(BracketError, match="one of the two players"):
            service.report_result(slug, match["match_no"], "u1", "u5")

    def test_a_reporter_cannot_confirm_their_own_report(self, service, repo):
        slug, _ = published(service, repo, 8)
        match = self._first_match(service, slug)
        service.report_result(slug, match["match_no"], "u1", "u1")
        with pytest.raises(BracketError, match="opponent has to confirm"):
            service.confirm_result(slug, match["match_no"], "u1", agree=True)

    def test_a_match_cannot_be_reported_twice(self, service, repo):
        slug, _ = published(service, repo, 8)
        match = self._first_match(service, slug)
        service.report_result(slug, match["match_no"], "u1", "u1")
        with pytest.raises(BracketError, match="already been reported"):
            service.report_result(slug, match["match_no"], "u8", "u8")

    def test_disputing_puts_the_match_back_for_reporting(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)

        service.report_result(slug, match["match_no"], "u1", "u1")
        result = service.confirm_result(slug, match["match_no"], "u8", agree=False)

        assert result["state"] == "disputed"
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["state"] == "pending"
        assert stored["reported_winner_id"] is None
        # And it can be reported again, by either player.
        service.report_result(slug, match["match_no"], "u8", "u8")

    def test_undecided_matches_cannot_be_reported(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        semi = next(
            m for m in repo.get_matches(bracket_id) if m["round"] == 2
        )
        with pytest.raises(BracketError, match="not decided yet"):
            service.report_result(slug, semi["match_no"], "u1", "u1")

    def test_reporting_is_closed_while_a_bracket_is_a_draft(self, service):
        service.create_bracket(name="Cup", size=4, source="overall")
        with pytest.raises(BracketError, match="not been published"):
            service.report_result("cup", 1, "u1", "u1")

    def test_expired_reports_confirm_themselves(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)
        service.report_result(slug, match["match_no"], "u1", "u1")

        # Wind the confirmation window back into the past.
        repo.update_match(bracket_id, match["match_no"], {"expires_at": int(time.time()) - 1})
        confirmed = service.auto_confirm_expired()

        assert confirmed == [{"slug": slug, "match_no": match["match_no"]}]
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["state"] == "complete"
        assert stored["resolved_by"] == "auto"

    def test_a_live_report_is_not_auto_confirmed(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)
        service.report_result(slug, match["match_no"], "u1", "u1")
        assert service.auto_confirm_expired() == []

    def test_open_matches_tell_a_player_what_they_owe(self, service, repo):
        slug, _ = published(service, repo, 8)
        match = self._first_match(service, slug)

        assert [m["needs"] for m in service.get_player_open_matches("u1")] == ["report"]

        service.report_result(slug, match["match_no"], "u1", "u1")
        assert service.get_player_open_matches("u1") == []
        assert [m["needs"] for m in service.get_player_open_matches("u8")] == ["confirm"]

    def test_winning_the_final_completes_the_bracket(self, service, repo):
        slug, bracket_id = published(service, repo, 2)
        final = repo.get_matches(bracket_id)[0]

        service.report_result(slug, final["match_no"], "u1", "u1")
        service.confirm_result(slug, final["match_no"], "u2", agree=True)

        bracket = repo.get_bracket(bracket_id=bracket_id)
        assert bracket["status"] == "complete"
        assert bracket["completed_at"]
        assert service.get_bracket_detail(slug)["champion"]["display_name"] == "P1"


class TestAdminOverrides:
    def test_admin_can_settle_a_match(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = repo.get_matches(bracket_id)[0]

        service.set_result(slug, match["match_no"], "u8", admin_id="admin_user_1")
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["winner_user_id"] == "u8"
        assert stored["resolved_by"] == "admin_user_1"

    def test_correcting_a_result_clears_the_downstream_slot(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = repo.get_matches(bracket_id)[0]

        service.set_result(slug, match["match_no"], "u1", admin_id="admin_user_1")
        service.set_result(slug, match["match_no"], "u8", admin_id="admin_user_1")

        parent = repo.get_match(bracket_id, match["next_match_no"])
        assert parent[f"p{match['next_slot']}_user_id"] == "u8"

    def test_resetting_a_match_undoes_it_and_the_rounds_above(self, service, repo):
        slug, bracket_id = published(service, repo, 4)
        matches = repo.get_matches(bracket_id)
        first, second = matches[0], matches[1]

        service.set_result(slug, first["match_no"], "u1", admin_id="a")
        service.set_result(slug, second["match_no"], "u2", admin_id="a")
        final = repo.get_match(bracket_id, first["next_match_no"])
        service.set_result(slug, final["match_no"], "u1", admin_id="a")
        assert repo.get_bracket(bracket_id=bracket_id)["status"] == "complete"

        service.reset_match(slug, first["match_no"])

        assert repo.get_match(bracket_id, first["match_no"])["state"] == "pending"
        cleared = repo.get_match(bracket_id, final["match_no"])
        assert cleared["winner_user_id"] is None
        assert cleared[f"p{first['next_slot']}_user_id"] is None
        assert repo.get_bracket(bracket_id=bracket_id)["status"] == "published"


# -- API ----------------------------------------------------------


class TestBracketApi:
    @pytest.fixture(autouse=True)
    def _seed_players(self, elo_db, match_db):
        seed_elo_data(elo_db, [
            {"user_id": "p_one", "name": "One", "online_event_elo": 1900},
            {"user_id": "p_two", "name": "Two", "online_event_elo": 1800},
        ])
        seed_matches(match_db, [
            {"winner_id": "p_one", "winner_name": "One", "loser_id": "p_two", "loser_name": "Two"},
        ])

    def _create_and_publish(self, admin_session, name="API Cup"):
        created = admin_session.post(
            "/api/admin/brackets", json={"name": name, "size": 2, "source": "overall"}
        ).get_json()
        admin_session.post(f"/api/admin/brackets/{created['slug']}/publish")
        return created["slug"]

    def test_list_is_public(self, client):
        resp = client.get("/api/brackets")
        assert resp.status_code == 200
        assert resp.get_json() == {"success": True, "brackets": []}

    def test_unknown_bracket_is_404(self, client):
        assert client.get("/api/brackets/nope").status_code == 404

    def test_creating_a_bracket_requires_admin(self, client):
        resp = client.post("/api/brackets" , json={})
        assert resp.status_code in (404, 405)
        resp = client.post("/api/admin/brackets", json={"name": "X", "size": 2})
        assert resp.status_code in (401, 403)

    def test_create_publish_and_read_back(self, admin_session):
        slug = self._create_and_publish(admin_session)

        detail = admin_session.get(f"/api/brackets/{slug}").get_json()
        assert detail["bracket"]["status"] == "published"
        assert len(detail["rounds"]) == 1
        assert detail["rounds"][0]["title"] == "Finals"
        assert detail["entrants"][0]["display_name"] == "One"

    def test_drafts_are_not_public_but_are_visible_to_admins(self, admin_session, client):
        created = admin_session.post(
            "/api/admin/brackets", json={"name": "Draft Cup", "size": 2, "source": "overall"}
        ).get_json()
        assert client.get(f"/api/brackets/{created['slug']}").status_code == 404
        assert admin_session.get(f"/api/admin/brackets/{created['slug']}").status_code == 200

    def test_reporting_requires_login(self, app, admin_session):
        slug = self._create_and_publish(admin_session)
        # A second client, with no session of its own.
        anonymous = app.test_client()
        resp = anonymous.post(
            f"/api/brackets/{slug}/matches/1/report", json={"winner_user_id": "p_one"}
        )
        assert resp.status_code in (401, 403)

    def test_a_player_reports_their_own_match(self, admin_session, client):
        slug = self._create_and_publish(admin_session)

        with client.session_transaction() as sess:
            sess["user_id"] = "p_one"
            sess["username"] = "One"

        resp = client.post(
            f"/api/brackets/{slug}/matches/1/report", json={"winner_user_id": "p_one"}
        )
        assert resp.status_code == 200
        assert resp.get_json()["awaiting"] == "Two"

        # The opponent's confirmation finishes it.
        with client.session_transaction() as sess:
            sess["user_id"] = "p_two"
        resp = client.post(f"/api/brackets/{slug}/matches/1/confirm", json={"agree": True})
        assert resp.status_code == 200

        detail = client.get(f"/api/brackets/{slug}").get_json()
        assert detail["champion"]["display_name"] == "One"

    def test_a_bystander_cannot_report(self, app, admin_session):
        slug = self._create_and_publish(admin_session)

        bystander = app.test_client()
        with bystander.session_transaction() as sess:
            sess["user_id"] = "someone_else"
            sess["username"] = "Someone Else"

        resp = bystander.post(
            f"/api/brackets/{slug}/matches/1/report", json={"winner_user_id": "p_one"}
        )
        assert resp.status_code == 400
        assert "Only the two players" in resp.get_json()["error"]

    def test_report_requires_a_winner(self, admin_session, client):
        slug = self._create_and_publish(admin_session)
        with client.session_transaction() as sess:
            sess["user_id"] = "p_one"
        resp = client.post(f"/api/brackets/{slug}/matches/1/report", json={})
        assert resp.status_code == 400

    def test_the_bracket_tells_the_viewer_what_they_can_do(self, admin_session, client):
        slug = self._create_and_publish(admin_session)
        with client.session_transaction() as sess:
            sess["user_id"] = "p_one"

        match = client.get(f"/api/brackets/{slug}").get_json()["rounds"][0]["matches"][0]
        assert match["viewer_is_player"] is True
        assert match["viewer_can_report"] is True
        assert match["viewer_can_confirm"] is False

    def test_my_matches_lists_what_a_player_owes(self, admin_session, client):
        self._create_and_publish(admin_session)
        with client.session_transaction() as sess:
            sess["user_id"] = "p_two"

        matches = client.get("/api/brackets/my-matches").get_json()["matches"]
        assert [m["needs"] for m in matches] == ["report"]

    def test_admin_seeding_tools(self, admin_session):
        created = admin_session.post(
            "/api/admin/brackets", json={"name": "Seeded", "size": 2, "source": "overall"}
        ).get_json()
        slug = created["slug"]

        assert admin_session.post(f"/api/admin/brackets/{slug}/shuffle").status_code == 200
        assert admin_session.post(
            f"/api/admin/brackets/{slug}/move", json={"seed": 2, "to_seed": 1}
        ).status_code == 200

        entrants = admin_session.get(f"/api/admin/brackets/{slug}").get_json()["entrants"]
        assert len(entrants) == 2

        resp = admin_session.put(
            f"/api/admin/brackets/{slug}/entrants",
            json={"entrants": [{"display_name": "Guest A"}, {"display_name": "Guest B"}]},
        )
        assert resp.get_json()["entrant_count"] == 2

    def test_seed_pool_endpoint(self, admin_session):
        pool = admin_session.get("/api/admin/brackets/seed-pool").get_json()
        assert pool["success"] is True
        assert "ticket_sync_configured" in pool
        assert [p["display_name"] for p in pool["players"]] == ["One", "Two"]

    def test_admin_can_override_and_reset_a_result(self, admin_session):
        slug = self._create_and_publish(admin_session)

        assert admin_session.post(
            f"/api/admin/brackets/{slug}/matches/1/result", json={"winner_user_id": "p_two"}
        ).status_code == 200
        assert admin_session.get(f"/api/brackets/{slug}").get_json()["champion"][
            "display_name"
        ] == "Two"

        assert admin_session.post(
            f"/api/admin/brackets/{slug}/matches/1/reset"
        ).status_code == 200
        assert admin_session.get(f"/api/brackets/{slug}").get_json()["champion"] is None

    def test_delete(self, admin_session):
        slug = self._create_and_publish(admin_session)
        assert admin_session.delete(f"/api/admin/brackets/{slug}").status_code == 200
        assert admin_session.delete(f"/api/admin/brackets/{slug}").status_code == 404
