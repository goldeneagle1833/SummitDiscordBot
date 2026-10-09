"""Tests for bracket seeding, publishing, and player-reported results."""

import json
import time

import pytest

import services.brackets as brackets_module
import utils.card_images as card_images
from repositories.brackets import BracketRepository
from services.bracket_builder import (
    bracket_size_for,
    build_matches,
    champion,
    round_title,
    seed_order,
)
from services.brackets import BracketError, BracketService, rounds_for_display, slugify
from tests.conftest import seed_elo_data, seed_matches


def make_entrants(count):
    return [
        {"user_id": f"u{i}", "display_name": f"P{i}", "elo": 2000 - i}
        for i in range(1, count + 1)
    ]


@pytest.fixture(autouse=True)
def events_dir(tmp_path, monkeypatch):
    """Where a finished bracket's Top 8 event lands.

    Finishing a bracket writes an event folder, so every test here - the
    route tests included - must point that at a temp folder rather than the
    real top-8-decks-by-event directory.
    """
    import repositories.events as events_module

    path = tmp_path / "top-8-decks-by-event"
    path.mkdir()
    monkeypatch.setattr(events_module, "TOP_8_DIR", path)
    return path


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


class FakeCuriosa:
    """Returns a deck without calling out to Curiosa."""

    def __init__(self, deck=None):
        self.deck = (
            deck
            if deck is not None
            else {
                "id": "abc123",
                "name": "Dead Cant Swim",
                "avatar": [{"name": "Necromancer", "identifier": "necromancer"}],
                "spellbook": [{"name": "Daperyll Vampire", "quantity": 3}],
            }
        )
        self.calls = []

    def fetch_deck_data(self, url):
        self.calls.append(url)
        return json.dumps(self.deck)


@pytest.fixture()
def curiosa():
    return FakeCuriosa()


@pytest.fixture()
def ladder(elo_db):
    """The bot ladder a bracket result moves."""
    from repositories.elo import EloRepository

    seed_elo_data(elo_db, [
        {"user_id": f"u{i}", "name": f"P{i}", "online_elo": 1500} for i in range(1, 25)
    ])
    return EloRepository(db_path=elo_db)


@pytest.fixture()
def match_log(match_db):
    """The online match log a bracket result is written into."""
    from repositories.matches import MatchRepository

    return MatchRepository(db_path=match_db)


@pytest.fixture()
def announcements():
    """Pairing DMs the service asked the bot to send."""
    return []


@pytest.fixture()
def batches():
    """Each call the service made to the bot."""
    return []


@pytest.fixture()
def service(repo, curiosa, ladder, match_log, announcements, batches):
    return BracketService(
        repo=repo,
        leaderboard_service=FakeLeaderboard(),
        curiosa_service=curiosa,
        elo_repo=ladder,
        match_repo=match_log,
        pairing_notifier=lambda batch: (
            batches.append(batch), announcements.extend(batch["pairings"])
        ),
    )


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


class TestDisplayRounds:
    """Byes are bookkeeping, not matches, so they are not drawn."""

    def test_a_24_player_field_opens_with_eight_pairs(self):
        rounds = rounds_for_display(build_matches(make_entrants(24)))
        assert [len(r["matches"]) for r in rounds] == [8, 8, 4, 2, 1]

    def test_bye_players_appear_in_round_two_tagged(self):
        rounds = rounds_for_display(build_matches(make_entrants(24)))
        second = rounds[1]["matches"]
        waiting = [m["p1_name"] for m in second if m["p1_from_bye"]]
        # The top eight seeds sat out round one.
        assert sorted(waiting, key=lambda n: int(n[1:])) == [f"P{i}" for i in range(1, 9)]
        assert all(m["p2_from_bye"] is False for m in second)

    def test_no_bye_cards_are_returned(self):
        for count in (3, 5, 13, 24):
            rounds = rounds_for_display(build_matches(make_entrants(count)))
            states = [m["state"] for r in rounds for m in r["matches"]]
            assert "bye" not in states
            assert "empty" not in states

    def test_a_full_field_is_unaffected(self):
        rounds = rounds_for_display(build_matches(make_entrants(8)))
        assert [len(r["matches"]) for r in rounds] == [4, 2, 1]
        assert all(not m["p1_from_bye"] for r in rounds for m in r["matches"])

    def test_rounds_with_nothing_to_draw_are_dropped(self):
        """A 3-player field has one real first-round match, not two."""
        rounds = rounds_for_display(build_matches(make_entrants(3)))
        assert [len(r["matches"]) for r in rounds] == [1, 1]
        assert rounds[0]["matches"][0]["p1_name"] == "P2"


class TestPreview:
    def test_preview_shows_the_tree_without_saving(self, service, repo):
        created = service.create_bracket(name="Preview Cup", size=24, source="overall")
        service.set_entrants(created["bracket_id"], make_entrants(24))

        preview = service.preview(created["bracket_id"])

        assert preview["bracket_size"] == 32
        assert preview["byes"] == 8
        assert [len(r["matches"]) for r in preview["rounds"]] == [8, 8, 4, 2, 1]
        # Nothing was persisted: the bracket is still an unpublished draft.
        assert repo.get_matches(created["bracket_id"]) == []
        assert repo.get_bracket(bracket_id=created["bracket_id"])["status"] == "draft"

    def test_preview_follows_the_seeding_order(self, service):
        created = service.create_bracket(name="Preview Cup", size=8, source="overall")
        first = service.preview(created["bracket_id"])["rounds"][0]["matches"][0]
        assert (first["p1_name"], first["p2_name"]) == ("P1", "P8")

        service.move_entrant(created["bracket_id"], 8, 1)
        moved = service.preview(created["bracket_id"])["rounds"][0]["matches"][0]
        assert (moved["p1_name"], moved["p2_name"]) == ("P8", "P7")

    def test_preview_of_an_empty_draft(self, service):
        created = service.create_bracket(name="Empty", size=8, source="manual")
        assert service.preview(created["bracket_id"]) == {
            "entrants": [], "rounds": [], "bracket_size": 0, "byes": 0,
        }

    def test_preview_of_a_missing_bracket(self, service):
        with pytest.raises(BracketError):
            service.preview(9999)


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

    def test_a_table_result_waits_for_either_player_to_confirm(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)

        state = service.record_table_result(bracket_id, match["match_no"], "u8")

        assert state == "reported"
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["reported_by"] == service.TABLE_REPORTER
        assert stored["reported_winner_id"] == "u8"
        assert stored["expires_at"] > time.time()
        assert [m["needs"] for m in service.get_player_open_matches("u1")] == ["confirm"]
        assert [m["needs"] for m in service.get_player_open_matches("u8")] == ["confirm"]

        service.confirm_result(slug, match["match_no"], "u1", agree=True)
        assert repo.get_match(bracket_id, match["match_no"])["winner_user_id"] == "u8"

    def test_a_disputed_table_result_goes_back_for_reporting(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)
        service.record_table_result(bracket_id, match["match_no"], "u8")

        assert service.confirm_result(slug, match["match_no"], "u1", agree=False) == {
            "state": "disputed"
        }
        assert repo.get_match(bracket_id, match["match_no"])["state"] == "pending"

    def test_a_table_result_never_overrides_a_players_report(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)
        service.report_result(slug, match["match_no"], "u1", "u1")

        assert service.record_table_result(bracket_id, match["match_no"], "u8") == "reported"
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["reported_by"] == "u1"
        assert stored["reported_winner_id"] == "u1"

    def test_a_table_result_names_one_of_the_players(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        match = self._first_match(service, slug)
        with pytest.raises(BracketError, match="one of the two players"):
            service.record_table_result(bracket_id, match["match_no"], "stranger")

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


class TestSwappingPlayers:
    """Re-pairing a published bracket before the affected matches are played.

    An 8-player field opens 1v8, 4v5, 2v7, 3v6. A 6-player field gives seeds 1
    and 2 byes, so it opens 4v5 and 3v6 with 1 and 2 waiting in round two.
    """

    def _pair(self, repo, bracket_id, match_no):
        m = repo.get_match(bracket_id, match_no)
        return (m["p1_seed"], m["p2_seed"])

    def test_two_first_round_players_trade_seats(self, service, repo):
        slug, bracket_id = published(service, repo, 8)

        result = service.swap_players(slug, 8, 5)

        assert self._pair(repo, bracket_id, 1) == (1, 5)
        assert self._pair(repo, bracket_id, 2) == (4, 8)
        stored = repo.get_match(bracket_id, 1)
        assert stored["p2_user_id"] == "u5"
        assert stored["p2_name"] == "P5"
        assert result["swapped"] == ["P8", "P5"]

    def test_a_swapped_player_can_report_their_new_match(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        service.swap_players(slug, 8, 5)

        service.report_result(slug, 1, "u5", "u5")
        service.confirm_result(slug, 1, "u1")
        assert repo.get_match(bracket_id, 5)["p1_user_id"] == "u5"

    def test_swapping_a_bye_moves_the_bye(self, service, repo):
        slug, bracket_id = published(service, repo, 6)
        # Round two, first match: seed 1 off a bye, waiting on 4v5.
        assert self._pair(repo, bracket_id, 5) == (1, None)

        service.swap_players(slug, 1, 6)

        assert self._pair(repo, bracket_id, 5) == (6, None)
        assert self._pair(repo, bracket_id, 4) == (3, 1)
        bye = repo.get_match(bracket_id, 1)
        assert bye["state"] == "bye"
        assert (bye["winner_seed"], bye["winner_user_id"]) == (6, "u6")

        rounds = rounds_for_display(repo.get_matches(bracket_id))
        second_round = rounds[1]["matches"][0]
        assert second_round["p1_from_bye"] is True
        assert second_round["p1_name"] == "P6"

    def test_a_played_match_cannot_be_re_paired(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        service.set_result(slug, 1, "u1", admin_id="a")

        with pytest.raises(BracketError, match="already been played"):
            service.swap_players(slug, 8, 5)
        # The winner's round-two seat is a result, not a pairing.
        with pytest.raises(BracketError, match="already"):
            service.swap_players(slug, 1, 5)

    def test_a_reported_match_cannot_be_re_paired(self, service, repo):
        slug, _ = published(service, repo, 8)
        service.report_result(slug, 1, "u1", "u1")

        with pytest.raises(BracketError, match="waiting to be confirmed"):
            service.swap_players(slug, 1, 5)

    def test_a_match_with_a_table_cannot_be_re_paired(self, service, repo):
        slug, bracket_id = published(service, repo, 8)
        repo.update_match(bracket_id, 2, {"table_provisioned_at": "2026-10-01T12:00:00"})

        with pytest.raises(BracketError, match="Sorcery Online table"):
            service.swap_players(slug, 1, 5)
        assert self._pair(repo, bracket_id, 1) == (1, 8)

    def test_opponents_cannot_be_swapped_with_each_other(self, service, repo):
        slug, _ = published(service, repo, 8)
        with pytest.raises(BracketError, match="already playing each other"):
            service.swap_players(slug, 1, 8)

    def test_drafts_use_the_seeding_list(self, service):
        created = service.create_bracket(name="Draft", size=8, source="overall")
        with pytest.raises(BracketError, match="seeding list"):
            service.swap_players(created["slug"], 1, 5)

    def test_unknown_seed(self, service, repo):
        slug, _ = published(service, repo, 8)
        with pytest.raises(BracketError, match="not in this bracket"):
            service.swap_players(slug, 1, 42)

    def test_the_tree_marks_which_seats_can_move(self, service, repo):
        slug, bracket_id = published(service, repo, 6)
        service.set_result(slug, 2, "u4", admin_id="a")

        rounds = rounds_for_display(repo.get_matches(bracket_id))
        first = {m["match_no"]: m for m in rounds[0]["matches"]}
        second = {m["match_no"]: m for m in rounds[1]["matches"]}

        assert (first[2]["p1_movable"], first[2]["p2_movable"]) == (False, False)
        assert (first[4]["p1_movable"], first[4]["p2_movable"]) == (True, True)
        # Seed 1 came off a bye and can move; seed 4 got there by winning.
        assert second[5]["p1_movable"] is True
        assert second[5]["p2_movable"] is False


class TestTop8Event:
    """A finished bracket is written out as an event on the Top 8 page."""

    def _deck(self, seed):
        return {
            "id": f"deck{seed}",
            "name": f"Deck {seed}",
            "username": f"curiosa_builder_{seed}",
            "avatar": [{"name": "Sparkmage", "identifier": "sparkmage"}],
            "spellbook": [{"name": "Spark", "quantity": 4, "elements": "Fire"}],
        }

    def _finish(self, service, repo, count, winners):
        """Publish a bracket, file every deck, and play it out.

        ``winners`` names the winning seed of each match in match order.
        """
        slug, bracket_id = published(service, repo, count)
        for entrant in repo.get_entrants(bracket_id):
            repo.upsert_deck(
                bracket_id,
                entrant["seed"],
                {
                    "user_id": entrant["user_id"],
                    "deck_url": f"https://curiosa.io/decks/deck{entrant['seed']}",
                    "deck_json": json.dumps(self._deck(entrant["seed"])),
                },
            )
        for match_no, seed in winners:
            service.set_result(slug, match_no, f"u{seed}", admin_id="a")
        return slug, bracket_id

    def _events(self, events_dir):
        from repositories.events import EventRepository

        return EventRepository(events_dir=events_dir)

    def test_finishing_the_final_adds_the_event(self, service, repo, events_dir):
        # 1v8, 4v5, 2v7, 3v6 -> 1 beats 4, 2 beats 3 -> 2 wins the final.
        _, bracket_id = self._finish(
            service, repo, 8, [(1, 1), (2, 4), (3, 2), (4, 3), (5, 1), (6, 2), (7, 2)]
        )

        folder = repo.get_bracket(bracket_id=bracket_id)["event_folder"]
        assert folder and folder.startswith("Test Cup ")

        events = self._events(events_dir)
        listed = next(e for e in events.get_all_events() if e["folder"] == folder)
        assert listed["name"] == "Test Cup"
        assert listed["winner_username"] == "P2"
        assert listed["event_date"] == repo.get_bracket(bracket_id=bracket_id)["completed_at"][:10]

        top8 = events.get_event_decks(folder)["top8_decks"]
        # Champion, finalist, semifinal losers by seed, quarterfinal losers by seed.
        assert [d["player"] for d in top8] == ["P2", "P1", "P3", "P4", "P5", "P6", "P7", "P8"]
        assert top8[0]["deck_name"] == "Deck 2"

    def test_the_bracket_games_become_the_match_history(self, service, repo, events_dir):
        _, bracket_id = self._finish(service, repo, 4, [(1, 1), (2, 2), (3, 1)])
        folder = repo.get_bracket(bracket_id=bracket_id)["event_folder"]

        history = self._events(events_dir).get_event_match_history(folder)
        champion_row = history["by_deck_id"]["deck1"]
        assert (champion_row["wins"], champion_row["losses"]) == (2, 0)
        final, semi = champion_row["matches"]
        assert final["result"] == "Win"
        assert final["opponent"]["display_name"] == "P2"
        assert semi["opponent"]["deck_id"] == "deck4"
        assert semi["phase"] == "SingleElimination"

    def test_a_field_past_eight_keeps_the_rest_as_all_decks(self, service, repo, events_dir):
        slug, bracket_id = published(service, repo, 10)
        for entrant in repo.get_entrants(bracket_id):
            repo.upsert_deck(
                bracket_id,
                entrant["seed"],
                {"user_id": entrant["user_id"], "deck_json": json.dumps(self._deck(entrant["seed"]))},
            )
        # Play every match the moment both seats are filled, top seed winning.
        while repo.get_bracket(bracket_id=bracket_id)["status"] != "complete":
            for m in repo.get_matches(bracket_id):
                if m["state"] == "pending" and m["p1_seed"] and m["p2_seed"]:
                    winner = min(m["p1_seed"], m["p2_seed"])
                    service.set_result(slug, m["match_no"], f"u{winner}", admin_id="a")
                    break

        folder = repo.get_bracket(bracket_id=bracket_id)["event_folder"]
        decks = self._events(events_dir).get_event_decks(folder)
        assert len(decks["top8_decks"]) == 8
        assert len(decks["all_decks"]) == 10
        assert decks["top8_decks"][0]["player"] == "P1"

    def test_a_corrected_final_rewrites_the_same_event(self, service, repo, events_dir):
        slug, bracket_id = self._finish(service, repo, 4, [(1, 1), (2, 2), (3, 1)])
        folder = repo.get_bracket(bracket_id=bracket_id)["event_folder"]
        events = self._events(events_dir)
        events.update_event_metadata(folder, rating=3, description="Season finale")

        service.set_result(slug, 3, "u2", admin_id="a")

        assert repo.get_bracket(bracket_id=bracket_id)["event_folder"] == folder
        assert [p.name for p in events_dir.iterdir() if p.is_dir()] == [folder]
        top8 = events.get_event_decks(folder)["top8_decks"]
        assert [d["player"] for d in top8[:2]] == ["P2", "P1"]
        listed = next(e for e in events.get_all_events() if e["folder"] == folder)
        assert listed["rating"] == 3
        assert events.get_event_description(folder) == "Season finale"

    def test_an_unfinished_bracket_is_not_added(self, service, repo, events_dir):
        slug, bracket_id = published(service, repo, 4)
        with pytest.raises(BracketError, match="finished"):
            service.publish_to_top8(bracket_id)
        assert not any(events_dir.iterdir())

    def test_a_bracket_without_decks_still_finishes(self, service, repo, events_dir):
        slug, bracket_id = published(service, repo, 2)
        service.set_result(slug, 1, "u1", admin_id="a")

        bracket = repo.get_bracket(bracket_id=bracket_id)
        assert bracket["status"] == "complete"
        assert bracket["event_folder"] is None
        with pytest.raises(BracketError, match="decklist"):
            service.publish_to_top8(bracket_id)

    def test_folder_names_do_not_collide(self, service, repo, events_dir):
        (events_dir / "placeholder").mkdir()
        _, first = self._finish(service, repo, 2, [(1, 1)])
        folder = repo.get_bracket(bracket_id=first)["event_folder"]

        from services.brackets import BracketService as Service
        bracket = {**repo.get_bracket(bracket_id=first), "event_folder": None}
        assert Service._top8_folder_name(bracket, self._events(events_dir)) == f"{folder} 2"

    def test_unsafe_characters_are_dropped_from_the_folder(self, service, repo, events_dir):
        created = service.create_bracket(name="Summit: Finals / 2026!", size=2, source="overall")
        service.publish(created["bracket_id"])
        repo.upsert_deck(created["bracket_id"], 1, {"deck_json": json.dumps(self._deck(1))})
        service.set_result(created["slug"], 1, "u1", admin_id="a")

        folder = repo.get_bracket(bracket_id=created["bracket_id"])["event_folder"]
        assert folder.startswith("Summit Finals 2026 ")
        assert (events_dir / folder).is_dir()


class TestDecklists:
    def _publish(self, service, repo, count=4):
        return published(service, repo, count, name="Deck Cup")

    def test_a_player_submits_their_own_deck(self, service, repo, curiosa):
        slug, bracket_id = self._publish(service, repo)

        result = service.submit_deck(slug, "https://curiosa.io/decks/abc123", actor_id="u2")

        assert result["seed"] == 2
        assert result["avatar_name"] == "Necromancer"
        assert curiosa.calls == ["https://curiosa.io/decks/abc123"]
        assert repo.get_deck(bracket_id, 2)["deck_name"] == "Dead Cant Swim"

    def test_resubmitting_replaces_the_deck(self, service, repo):
        slug, bracket_id = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/one", actor_id="u2")
        service.submit_deck(slug, "https://curiosa.io/decks/two", actor_id="u2")

        assert len(repo.get_decks(bracket_id)) == 1
        assert repo.get_deck(bracket_id, 2)["deck_url"].endswith("two")

    def test_the_detail_counts_who_still_owes_a_deck(self, service, repo):
        slug, _ = self._publish(service, repo, count=4)
        assert service.get_bracket_detail(slug)["decks_missing"] == 4

        service.submit_deck(slug, "https://curiosa.io/decks/one", actor_id="u1")
        assert service.get_bracket_detail(slug)["decks_missing"] == 3

        for seed in (2, 3, 4):
            service.submit_deck(slug, f"https://curiosa.io/decks/{seed}", actor_id=f"u{seed}")
        assert service.get_bracket_detail(slug)["decks_missing"] == 0

    def test_someone_outside_the_bracket_cannot_submit(self, service, repo):
        slug, _ = self._publish(service, repo)
        with pytest.raises(BracketError, match="not in this bracket"):
            service.submit_deck(slug, "https://curiosa.io/decks/x", actor_id="stranger")

    def test_a_draft_takes_no_decks(self, service):
        service.create_bracket(name="Draft Cup", size=4, source="overall")
        with pytest.raises(BracketError, match="once the bracket is published"):
            service.submit_deck("draft-cup", "https://curiosa.io/decks/x", actor_id="u1")

    def test_an_unreadable_link_is_rejected(self, repo):
        service = BracketService(
            repo=repo,
            leaderboard_service=FakeLeaderboard(),
            curiosa_service=FakeCuriosa(deck={}),
        )
        slug, _ = published(service, repo, 4, name="Deck Cup")
        with pytest.raises(BracketError, match="Could not read that deck"):
            service.submit_deck(slug, "https://example.com/not-a-deck", actor_id="u1")

    def test_an_empty_link_is_rejected(self, service, repo):
        slug, _ = self._publish(service, repo)
        with pytest.raises(BracketError, match="deck link is required"):
            service.submit_deck(slug, "   ", actor_id="u1")

    def test_submitting_snapshots_the_list(self, service, repo, curiosa):
        """The deck is captured as it was submitted, not read live later."""
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        # The player edits their Curiosa deck after submitting.
        curiosa.deck = {
            "name": "Rebuilt Overnight",
            "avatar": [{"name": "Witch"}],
            "spellbook": [{"name": "Something Else", "quantity": 1}],
        }

        stored = service.get_deck(slug, 1, viewer_id="u1")["deck"]
        assert stored["name"] == "Dead Cant Swim"
        assert stored["spellbook"][0]["name"] == "Daperyll Vampire"

    def test_resubmitting_takes_a_fresh_snapshot(self, service, repo, curiosa):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        curiosa.deck = {
            "name": "Rebuilt Overnight",
            "avatar": [{"name": "Witch"}],
            "spellbook": [{"name": "Something Else", "quantity": 1}],
        }
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        assert service.get_deck(slug, 1, viewer_id="u1")["deck"]["name"] == "Rebuilt Overnight"

    def test_the_snapshot_is_stamped_with_when_it_was_taken(self, service, repo):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        player = next(
            p for p in service.get_deck_roster(slug, viewer_id="u1")["players"] if p["seed"] == 1
        )
        assert player["submitted_at"]

    def test_a_live_players_deck_is_hidden_from_everyone_else(self, service, repo):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        roster = service.get_deck_roster(slug, viewer_id="u3")
        seed_one = next(p for p in roster["players"] if p["seed"] == 1)
        assert seed_one["has_deck"] is True
        assert seed_one["deck_visible"] is False
        assert seed_one["deck_url"] is None

        with pytest.raises(BracketError, match="stays hidden"):
            service.get_deck(slug, 1, viewer_id="u3")

    def test_a_player_can_always_see_their_own(self, service, repo):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        own = service.get_deck(slug, 1, viewer_id="u1")
        assert own["deck"]["name"] == "Dead Cant Swim"

    def test_an_admin_can_always_see(self, service, repo):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")
        assert service.get_deck(slug, 1, viewer_id="someone", is_admin=True)["deck"]["name"]

    def test_the_deck_opens_up_once_the_player_is_knocked_out(self, service, repo):
        slug, bracket_id = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u4")

        first = repo.get_matches(bracket_id)[0]  # seed 1 v seed 4
        service.set_result(slug, first["match_no"], "u1", admin_id="a")

        roster = service.get_deck_roster(slug, viewer_id="u3")
        loser = next(p for p in roster["players"] if p["seed"] == 4)
        assert loser["eliminated"] is True
        assert loser["deck_visible"] is True
        assert service.get_deck(slug, 4, viewer_id="u3")["deck"]["name"] == "Dead Cant Swim"

    def test_the_winners_deck_opens_up_when_the_bracket_ends(self, service, repo):
        slug, bracket_id = self._publish(service, repo, count=2)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        assert service.get_deck_roster(slug, viewer_id="u9")["players"][0]["deck_visible"] is False

        final = repo.get_matches(bracket_id)[0]
        service.set_result(slug, final["match_no"], "u1", admin_id="a")

        champ = service.get_deck_roster(slug, viewer_id="u9")["players"][0]
        assert champ["deck_visible"] is True

    def test_the_owner_is_told_only_they_can_see_it(self, service, repo):
        """A player reading "revealed" on their own row would panic."""
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        own = next(
            p for p in service.get_deck_roster(slug, viewer_id="u1")["players"] if p["seed"] == 1
        )
        assert own["visibility"] == "owner"
        assert own["deck_visible"] is True

    def test_others_see_it_as_hidden(self, service, repo):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        theirs = next(
            p for p in service.get_deck_roster(slug, viewer_id="u3")["players"] if p["seed"] == 1
        )
        assert theirs["visibility"] == "hidden"

    def test_an_admin_sees_it_flagged_as_an_admin_view(self, service, repo):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        seen = next(
            p
            for p in service.get_deck_roster(slug, viewer_id="admin_1", is_admin=True)["players"]
            if p["seed"] == 1
        )
        assert seen["visibility"] == "admin"

    def test_knocked_out_reads_as_public_even_to_the_owner(self, service, repo):
        slug, bracket_id = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u4")

        first = repo.get_matches(bracket_id)[0]  # seed 1 v seed 4
        service.set_result(slug, first["match_no"], "u1", admin_id="a")

        own = next(
            p for p in service.get_deck_roster(slug, viewer_id="u4")["players"] if p["seed"] == 4
        )
        assert own["visibility"] == "public"

    def test_players_with_no_deck_have_no_visibility(self, service, repo):
        slug, _ = self._publish(service, repo)
        roster = service.get_deck_roster(slug, viewer_id="u1")
        assert {p["visibility"] for p in roster["players"] if not p["has_deck"]} == {"none"}

    def test_roster_counts_who_still_owes_a_deck(self, service, repo):
        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        roster = service.get_deck_roster(slug, is_admin=True)
        assert (roster["submitted"], roster["missing"]) == (1, 3)
        assert [p["seed"] for p in roster["players"] if not p["has_deck"]] == [2, 3, 4]

    def test_only_the_owner_is_offered_the_submit_form(self, service, repo):
        slug, _ = self._publish(service, repo)
        roster = service.get_deck_roster(slug, viewer_id="u2")
        assert [p["seed"] for p in roster["players"] if p["can_submit"]] == [2]

    def test_an_admin_submits_for_a_player(self, service, repo):
        slug, bracket_id = self._publish(service, repo)

        result = service.submit_deck(
            slug, "https://curiosa.io/decks/abc", actor_id="admin_1", seed=3, is_admin=True
        )

        assert result["display_name"] == "P3"
        stored = repo.get_deck(bracket_id, 3)
        assert stored["submitted_by"] == "admin_1"
        assert stored["user_id"] == "u3"

    def test_an_admin_can_add_a_deck_for_a_guest_entrant(self, service, repo):
        created = service.create_bracket(name="Guest Cup", size=2, source="overall")
        service.set_entrants(created["bracket_id"], [
            {"display_name": "Guest A"},
            {"display_name": "Guest B"},
        ])
        service.publish(created["bracket_id"])

        result = service.submit_deck(
            "guest-cup", "https://curiosa.io/decks/abc", actor_id="admin_1", seed=1, is_admin=True
        )
        assert result["display_name"] == "Guest A"

    def test_admin_removes_a_deck(self, service, repo):
        slug, bracket_id = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        assert service.delete_deck(slug, 1) is True
        assert repo.get_deck(bracket_id, 1) is None
        assert service.delete_deck(slug, 1) is False

    def test_deleting_a_bracket_takes_its_decks(self, service, repo):
        slug, bracket_id = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        service.delete_bracket(bracket_id)
        assert repo.get_decks(bracket_id) == []

    def test_card_images_come_from_the_sites_own_set(self, service, repo, tmp_path, monkeypatch):
        """Curiosa hands back CDN urls; /card-images can only serve local files."""
        (tmp_path / "bet-daperyll_vampire-b-s.png").write_bytes(b"")
        monkeypatch.setattr(card_images, "CARD_IMAGES_DIR", tmp_path)
        card_images.reset_cache()

        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        deck = service.get_deck(slug, 1, viewer_id="u1", is_admin=True)["deck"]
        assert deck["spellbook"][0]["image"] == "bet-daperyll_vampire-b-s.png"
        card_images.reset_cache()

    def test_cards_with_no_local_image_are_left_blank(self, service, repo, tmp_path, monkeypatch):
        monkeypatch.setattr(card_images, "CARD_IMAGES_DIR", tmp_path)
        card_images.reset_cache()

        slug, _ = self._publish(service, repo)
        service.submit_deck(slug, "https://curiosa.io/decks/abc", actor_id="u1")

        deck = service.get_deck(slug, 1, viewer_id="u1", is_admin=True)["deck"]
        assert deck["spellbook"][0]["image"] is None
        card_images.reset_cache()

    def test_a_missing_deck_reads_clearly(self, service, repo):
        slug, _ = self._publish(service, repo)
        with pytest.raises(BracketError, match="No deck submitted"):
            service.get_deck(slug, 1, viewer_id="u1")

    def test_drafts_hide_the_roster_from_the_public(self, service):
        service.create_bracket(name="Draft Cup", size=4, source="overall")
        assert service.get_deck_roster("draft-cup") is None
        assert service.get_deck_roster("draft-cup", is_admin=True) is not None


class TestSorceryOnlineTables:
    """Opening a preloaded table for a pairing."""

    def _ready_match(self, service, repo, monkeypatch, calls=None,
                     replay_url="https://playsorceryonline.com/replay/table-1"):
        """A published 4-player bracket where seeds 1 and 4 both have decks."""
        slug, bracket_id = published(service, repo, 4, name="Table Cup")
        service.submit_deck(slug, "https://curiosa.io/decks/one", actor_id="u1")
        service.submit_deck(slug, "https://curiosa.io/decks/four", actor_id="u4")

        def fake_provision(pairing_id, players):
            if calls is not None:
                calls.append({"pairing_id": pairing_id, "players": players})
            return {
                "seats": {
                    str(p["user_id"]): f"https://playsorceryonline.com/play?m=seat-{p['user_id']}"
                    for p in players
                },
                "replay_url": replay_url,
            }

        monkeypatch.setattr(brackets_module, "provision_match_table", fake_provision)
        match = repo.get_matches(bracket_id)[0]  # seed 1 v seed 4
        return slug, bracket_id, match

    def test_opening_a_table_preloads_both_decks(self, service, repo, monkeypatch):
        calls = []
        slug, _, match = self._ready_match(service, repo, monkeypatch, calls)

        result = service.open_table(slug, match["match_no"], "u1")

        assert result["game_url"].endswith("seat-u1")
        assert result["reused"] is False
        sent = calls[0]["players"]
        assert [p["user_id"] for p in sent] == ["u1", "u4"]
        assert [p["deck_url"] for p in sent] == [
            "https://curiosa.io/decks/one",
            "https://curiosa.io/decks/four",
        ]

    def test_each_player_gets_their_own_seat_at_one_table(self, service, repo, monkeypatch):
        calls = []
        slug, _, match = self._ready_match(service, repo, monkeypatch, calls)

        first = service.open_table(slug, match["match_no"], "u1")
        second = service.open_table(slug, match["match_no"], "u4")

        assert first["game_url"] != second["game_url"]
        assert second["game_url"].endswith("seat-u4")
        assert second["reused"] is True
        # One table, not two.
        assert len(calls) == 1

    def test_a_missing_decklist_blocks_the_table(self, service, repo, monkeypatch):
        slug, bracket_id = published(service, repo, 4, name="Table Cup")
        service.submit_deck(slug, "https://curiosa.io/decks/one", actor_id="u1")
        monkeypatch.setattr(
            brackets_module, "provision_match_table",
            lambda *a, **k: pytest.fail("should not reach Sorcery Online"),
        )

        match = repo.get_matches(bracket_id)[0]
        with pytest.raises(BracketError, match="P4 still need"):
            service.open_table(slug, match["match_no"], "u1")

    def test_only_the_two_players_can_open_it(self, service, repo, monkeypatch):
        slug, _, match = self._ready_match(service, repo, monkeypatch)
        with pytest.raises(BracketError, match="Only the two players"):
            service.open_table(slug, match["match_no"], "u2")

    def test_a_settled_match_has_no_table(self, service, repo, monkeypatch):
        slug, _, match = self._ready_match(service, repo, monkeypatch)
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        with pytest.raises(BracketError, match="already settled"):
            service.open_table(slug, match["match_no"], "u1")

    def test_sorcery_online_being_down_reads_clearly(self, service, repo, monkeypatch):
        slug, _, match = self._ready_match(service, repo, monkeypatch)

        def refuse(pairing_id, players):
            raise brackets_module.TableUnavailable("Could not reach Sorcery Online.")

        monkeypatch.setattr(brackets_module, "provision_match_table", refuse)
        with pytest.raises(BracketError, match="Could not reach Sorcery Online"):
            service.open_table(slug, match["match_no"], "u1")

    def test_a_seat_link_is_only_shown_to_its_own_player(self, service, repo, monkeypatch):
        slug, _, match = self._ready_match(service, repo, monkeypatch)
        service.open_table(slug, match["match_no"], "u1")

        def first_match(viewer):
            detail = service.get_bracket_detail(slug, viewer_id=viewer)
            return detail["rounds"][0]["matches"][0]

        assert first_match("u1")["viewer_table_url"].endswith("seat-u1")
        assert first_match("u4")["viewer_table_url"].endswith("seat-u4")

        # Nobody else gets a link - not a bystander, not even an admin.
        assert first_match("u2")["viewer_table_url"] is None
        bystander = first_match("u2")
        assert "table_p1_url" not in bystander and "table_p2_url" not in bystander

    def test_opening_a_table_keeps_its_replay_url(self, service, repo, monkeypatch):
        """Sorcery Online hands the replay link back with the table."""
        slug, bracket_id, match = self._ready_match(service, repo, monkeypatch)

        service.open_table(slug, match["match_no"], "u1")

        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["replay_url"] == "https://playsorceryonline.com/replay/table-1"
        assert stored["replay_added_by"] == "sorcery-online"

    def test_a_table_without_a_replay_url_is_fine(self, service, repo, monkeypatch):
        slug, bracket_id, match = self._ready_match(service, repo, monkeypatch, replay_url=None)

        service.open_table(slug, match["match_no"], "u1")

        assert repo.get_match(bracket_id, match["match_no"])["replay_url"] is None

    def test_a_replay_an_admin_filed_is_not_overwritten(self, service, repo, monkeypatch):
        slug, bracket_id, match = self._ready_match(service, repo, monkeypatch)
        service.set_replay(
            slug, match["match_no"], "https://playsorceryonline.com/replay/mine", "admin_1"
        )

        service.open_table(slug, match["match_no"], "u1")

        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["replay_url"].endswith("/replay/mine")
        assert stored["replay_added_by"] == "admin_1"

    def test_the_captured_replay_is_held_until_the_game_is_played(self, service, repo, monkeypatch):
        """The link exists from the moment the table opens, but there is
        nothing to watch until the match has been played."""
        slug, bracket_id, match = self._ready_match(service, repo, monkeypatch)
        service.open_table(slug, match["match_no"], "u1")

        def first_match(**viewer):
            return service.get_bracket_detail(slug, **viewer)["rounds"][0]["matches"][0]

        assert first_match(viewer_id="u1")["replay_url"] is None
        assert first_match(viewer_id="x", is_admin=True)["replay_url"].endswith("/replay/table-1")

        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        # Played now: the two players can watch it, onlookers wait for the end.
        assert first_match(viewer_id="u1")["replay_url"].endswith("/replay/table-1")
        assert first_match(viewer_id="nobody")["replay_url"] is None

    def test_the_button_is_offered_only_when_both_decks_are_in(self, service, repo, monkeypatch):
        slug, bracket_id = published(service, repo, 4, name="Table Cup")
        service.submit_deck(slug, "https://curiosa.io/decks/one", actor_id="u1")

        match = service.get_bracket_detail(slug, viewer_id="u1")["rounds"][0]["matches"][0]
        assert match["viewer_can_open_table"] is False
        assert match["decks_missing"] == ["P4"]

        service.submit_deck(slug, "https://curiosa.io/decks/four", actor_id="u4")
        match = service.get_bracket_detail(slug, viewer_id="u1")["rounds"][0]["matches"][0]
        assert match["viewer_can_open_table"] is True
        assert match["decks_missing"] == []


class TestReplayLinks:
    def _played_match(self, service, repo):
        slug, bracket_id = published(service, repo, 4, name="Replay Cup")
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="admin_1")
        return slug, bracket_id, match

    def test_an_admin_attaches_a_replay(self, service, repo):
        slug, bracket_id, match = self._played_match(service, repo)

        result = service.set_replay(
            slug, match["match_no"], "https://playsorceryonline.com/replay/abc", "admin_1"
        )

        assert result["replay_url"].endswith("/replay/abc")
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["replay_added_by"] == "admin_1"
        assert stored["replay_added_at"]

    def test_only_sorcery_online_links_are_accepted(self, service, repo):
        slug, _, match = self._played_match(service, repo)
        with pytest.raises(BracketError, match="have to be Sorcery Online links"):
            service.set_replay(slug, match["match_no"], "https://youtube.com/watch?v=x", "admin_1")

    def test_an_empty_link_is_rejected(self, service, repo):
        slug, _, match = self._played_match(service, repo)
        with pytest.raises(BracketError, match="replay link is required"):
            service.set_replay(slug, match["match_no"], "  ", "admin_1")

    def test_a_replay_stays_private_until_the_bracket_ends(self, service, repo):
        slug, _, match = self._played_match(service, repo)
        service.set_replay(
            slug, match["match_no"], "https://playsorceryonline.com/replay/abc", "admin_1"
        )

        def first_match(**viewer):
            return service.get_bracket_detail(slug, **viewer)["rounds"][0]["matches"][0]

        # A passer-by sees nothing while the bracket is still running.
        assert first_match(viewer_id="nobody")["replay_url"] is None
        # The players in it, and admins, can see it.
        assert first_match(viewer_id="u1")["replay_url"].endswith("/replay/abc")
        assert first_match(viewer_id="x", is_admin=True)["replay_url"].endswith("/replay/abc")
        assert first_match(viewer_id="u1")["replay_public"] is False

    def test_it_opens_up_when_the_bracket_finishes(self, service, repo):
        slug, bracket_id = published(service, repo, 2, name="Replay Final")
        final = repo.get_matches(bracket_id)[0]
        service.set_result(slug, final["match_no"], "u1", admin_id="admin_1")
        service.set_replay(
            slug, final["match_no"], "https://playsorceryonline.com/replay/final", "admin_1"
        )

        seen = service.get_bracket_detail(slug, viewer_id="nobody")["rounds"][0]["matches"][0]
        assert seen["replay_url"].endswith("/replay/final")
        assert seen["replay_public"] is True

    def test_an_admin_can_remove_a_replay(self, service, repo):
        slug, bracket_id, match = self._played_match(service, repo)
        service.set_replay(
            slug, match["match_no"], "https://playsorceryonline.com/replay/abc", "admin_1"
        )

        assert service.clear_replay(slug, match["match_no"]) is True
        assert repo.get_match(bracket_id, match["match_no"])["replay_url"] is None
        assert service.clear_replay(slug, match["match_no"]) is False


class TestBracketElo:
    """Top cut games are history only: they move no ELO on any ladder."""

    def _elos(self, elo_db, *user_ids):
        import sqlite3

        conn = sqlite3.connect(str(elo_db))
        out = []
        for user_id in user_ids:
            row = conn.execute(
                "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            out.append(row)
        conn.close()
        return out

    def test_a_confirmed_result_moves_no_elo(self, service, repo, elo_db):
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]  # seed 1 v seed 4

        service.report_result(slug, match["match_no"], "u1", "u1")
        service.confirm_result(slug, match["match_no"], "u4", agree=True)

        (winner, loser) = self._elos(elo_db, "u1", "u4")
        assert winner == (1500, 1500)
        assert loser == (1500, 1500)

    def test_nothing_is_flagged_as_applied(self, service, repo):
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["elo_applied_at"] is None

    def test_a_full_run_moves_no_elo(self, service, repo, elo_db):
        slug, bracket_id = published(service, repo, 4)
        first, second = repo.get_matches(bracket_id)[0], repo.get_matches(bracket_id)[1]

        service.set_result(slug, first["match_no"], "u1", admin_id="a")
        service.set_result(slug, second["match_no"], "u2", admin_id="a")
        final = repo.get_match(bracket_id, first["next_match_no"])
        service.set_result(slug, final["match_no"], "u1", admin_id="a")
        service.set_result(slug, final["match_no"], "u2", admin_id="a")
        service.reset_match(slug, first["match_no"])

        for row in self._elos(elo_db, "u1", "u2", "u3", "u4"):
            assert row == (1500, 1500)


class TestBracketEloRefund:
    """Games settled while brackets still moved ELO get their points back."""

    def _legacy_result(self, service, repo, ladder):
        """A settled match as the old code left it: +16/-16 applied."""
        slug, bracket_id = published(service, repo, 4, name="Old Cup")
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")
        ladder.set_user_elo("u1", 1516)
        ladder.set_user_elo("u4", 1484)
        repo.update_match(
            bracket_id,
            match["match_no"],
            {"elo_applied_at": "2026-09-01T00:00:00", "winner_elo_change": 16, "loser_elo_change": -16},
        )
        # Logged to the running season, as bracket games used to be.
        stored = repo.get_match(bracket_id, match["match_no"])
        service._match_repo.delete_match_row(
            stored["match_record_id"], table="match_records_archive"
        )
        row_id = service._match_repo.insert_match({
            "winner_id": "u1", "losser_id": "u4", "source": "Bracket",
            "timestamp": "2026-09-01 12:00:00",
            "winner_elo_change": 16, "loser_elo_change": -16,
            "match_comment": "Old Cup - Round 1",
        })
        repo.update_match(
            bracket_id, match["match_no"],
            {"match_record_id": row_id, "match_record_table": None},
        )
        stored = repo.get_match(bracket_id, match["match_no"])
        return slug, bracket_id, stored

    def test_the_points_come_back(self, service, repo, ladder):
        self._legacy_result(service, repo, ladder)

        assert service.refund_applied_elo() == 1
        assert ladder.get_user_elo("u1") == 1500
        assert ladder.get_user_elo("u4") == 1500

    def test_it_only_refunds_once(self, service, repo, ladder):
        self._legacy_result(service, repo, ladder)

        service.refund_applied_elo()
        assert service.refund_applied_elo() == 0
        assert ladder.get_user_elo("u1") == 1500

    def test_the_history_row_is_relabelled(self, service, repo, ladder, match_db):
        import sqlite3

        _, _, stored = self._legacy_result(service, repo, ladder)
        service.refund_applied_elo()

        conn = sqlite3.connect(str(match_db))
        row = conn.execute(
            "SELECT match_comment, winner_elo_change, loser_elo_change FROM match_records"
            " WHERE rowid = ?",
            (stored["match_record_id"],),
        ).fetchone()
        conn.close()
        assert row[0].startswith("Top cut game")
        assert (row[1], row[2]) == (0, 0)

    def test_resetting_a_legacy_result_refunds_it(self, service, repo, ladder):
        slug, _, stored = self._legacy_result(service, repo, ladder)

        service.reset_match(slug, stored["match_no"])

        assert ladder.get_user_elo("u1") == 1500
        assert ladder.get_user_elo("u4") == 1500
        assert service.refund_applied_elo() == 0


class TestPairingAnnouncements:
    """Both players are DMed once their next match has both seats filled."""

    def _first_round(self, repo, bracket_id):
        return [m for m in repo.get_matches(bracket_id) if m["round"] == 1]

    def test_one_side_decided_announces_nothing(self, service, repo, announcements):
        slug, bracket_id = published(service, repo, 4)
        announcements.clear()  # round one, covered below
        first = self._first_round(repo, bracket_id)[0]

        service.set_result(slug, first["match_no"], first["p1_user_id"], admin_id="a")

        assert announcements == []

    def test_both_sides_decided_announces_the_pairing(self, service, repo, announcements):
        slug, bracket_id = published(service, repo, 4, name="Gothic Cup")
        announcements.clear()
        first, second = self._first_round(repo, bracket_id)[:2]
        service.submit_deck(slug, "https://curiosa.io/decks/one", actor_id=first["p1_user_id"])

        service.set_result(slug, first["match_no"], first["p1_user_id"], admin_id="a")
        service.set_result(slug, second["match_no"], second["p1_user_id"], admin_id="a")

        [sent] = announcements
        final = repo.get_match(bracket_id, first["next_match_no"])
        assert sent["bracket_name"] == "Gothic Cup"
        assert sent["round_title"] == final["round_title"]
        assert sent["first_round"] is False
        assert sent["bracket_url"].endswith(f"/brackets/{slug}")
        players = {p["user_id"]: p for p in sent["players"]}
        assert set(players) == {first["p1_user_id"], second["p1_user_id"]}
        assert players[first["p1_user_id"]]["opponent"]["user_id"] == second["p1_user_id"]
        assert players[first["p1_user_id"]]["deck_submitted"] is True
        assert players[second["p1_user_id"]]["deck_submitted"] is False

    def test_a_bye_holder_is_announced_when_their_opponent_arrives(
        self, service, repo, announcements
    ):
        slug, bracket_id = published(service, repo, 3)  # seed 1 has a bye
        announcements.clear()
        playable = next(
            m for m in self._first_round(repo, bracket_id) if m["state"] != "bye"
        )

        service.set_result(slug, playable["match_no"], playable["p1_user_id"], admin_id="a")

        [sent] = announcements
        assert "u1" in {p["user_id"] for p in sent["players"]}

    def test_re_confirming_the_same_result_does_not_repeat_it(
        self, service, repo, announcements
    ):
        slug, bracket_id = published(service, repo, 4)
        announcements.clear()  # round one, covered below
        first, second = self._first_round(repo, bracket_id)[:2]
        service.set_result(slug, first["match_no"], first["p1_user_id"], admin_id="a")
        service.set_result(slug, second["match_no"], second["p1_user_id"], admin_id="a")

        service.set_result(slug, second["match_no"], second["p1_user_id"], admin_id="a")

        assert len(announcements) == 1

    def test_a_corrected_result_announces_the_new_pairing(self, service, repo, announcements):
        slug, bracket_id = published(service, repo, 4)
        announcements.clear()  # round one, covered below
        first, second = self._first_round(repo, bracket_id)[:2]
        service.set_result(slug, first["match_no"], first["p1_user_id"], admin_id="a")
        service.set_result(slug, second["match_no"], second["p1_user_id"], admin_id="a")

        service.set_result(slug, second["match_no"], second["p2_user_id"], admin_id="a")

        assert len(announcements) == 2
        assert second["p2_user_id"] in {p["user_id"] for p in announcements[-1]["players"]}

    def test_a_failed_notifier_never_blocks_the_result(self, service, repo):
        def broken(payload):
            raise RuntimeError("bot is down")

        service._pairing_notifier = broken
        slug, bracket_id = published(service, repo, 4)
        first, second = self._first_round(repo, bracket_id)[:2]
        service.set_result(slug, first["match_no"], first["p1_user_id"], admin_id="a")

        service.set_result(slug, second["match_no"], second["p1_user_id"], admin_id="a")

        final = repo.get_match(bracket_id, first["next_match_no"])
        assert final["p1_user_id"] and final["p2_user_id"]


    def test_publishing_announces_every_first_round_pairing(
        self, service, repo, announcements
    ):
        slug, bracket_id = published(service, repo, 8)

        assert len(announcements) == 4
        assert all(a["first_round"] for a in announcements)
        paired = [{p["user_id"] for p in a["players"]} for a in announcements]
        assert {"u1", "u8"} in paired

    def test_publishing_sends_round_one_as_one_batch(self, service, repo, batches):
        published(service, repo, 8, name="Gothic Cup")

        [batch] = batches
        assert batch["bracket_name"] == "Gothic Cup"
        assert len(batch["pairings"]) == 4

    def test_a_bye_is_not_announced_as_a_pairing(self, service, repo, announcements):
        published(service, repo, 3)  # seed 1 has a bye; only 2 v 3 is played

        [sent] = announcements
        assert {p["user_id"] for p in sent["players"]} == {"u2", "u3"}

    def test_swapping_players_announces_the_new_pairings(self, service, repo, announcements):
        slug, bracket_id = published(service, repo, 4)
        announcements.clear()

        service.swap_players(slug, 1, 2)

        paired = [{p["user_id"] for p in a["players"]} for a in announcements]
        assert len(paired) == 2
        assert {"u2", "u4"} in paired
        assert {"u1", "u3"} in paired


class TestBracketMatchRecords:
    """A settled bracket game is a played match, and shows up as one."""

    def _rows(self, match_db, user_id=None):
        import sqlite3

        conn = sqlite3.connect(str(match_db))
        conn.row_factory = sqlite3.Row
        sql = "SELECT rowid, * FROM match_records_archive WHERE source = 'Bracket'"
        params = ()
        if user_id:
            sql += " AND (winner_id = ? OR losser_id = ?)"
            params = (user_id, user_id)
        try:
            rows = [dict(r) for r in conn.execute(sql, params)]
        except sqlite3.OperationalError:
            rows = []  # Nothing has been archived yet
        conn.close()
        return rows

    def test_settling_a_match_logs_it(self, service, repo, match_db):
        slug, bracket_id = published(service, repo, 4, name="Log Cup")
        match = repo.get_matches(bracket_id)[0]

        service.report_result(slug, match["match_no"], "u1", "u1")
        service.confirm_result(slug, match["match_no"], "u4", agree=True)

        rows = self._rows(match_db)
        assert len(rows) == 1
        assert rows[0]["winner_id"] == "u1"
        assert rows[0]["losser_id"] == "u4"
        assert rows[0]["match_type"] == "ranked"
        assert "Log Cup" in rows[0]["match_comment"]
        assert rows[0]["match_comment"].startswith("Top cut game")

    def test_the_logged_match_carries_no_rating_change(self, service, repo, match_db):
        slug, bracket_id = published(service, repo, 4, name="Log Cup")
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        row = self._rows(match_db)[0]
        assert (row["winner_elo_change"], row["loser_elo_change"]) == (0, 0)
        assert row["winner_lifetime_elo_after"] == 1500

    def test_the_logged_match_carries_both_decks(self, service, repo, match_db):
        slug, bracket_id = published(service, repo, 4, name="Log Cup")
        service.submit_deck(slug, "https://curiosa.io/decks/one", actor_id="u1")
        service.submit_deck(slug, "https://curiosa.io/decks/four", actor_id="u4")
        match = repo.get_matches(bracket_id)[0]

        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        row = self._rows(match_db)[0]
        assert row["curiosa_url_winner"].endswith("/one")
        assert row["curiosa_url_loser"].endswith("/four")
        assert "Dead Cant Swim" in row["json_deck_data_winner"]

    def test_it_counts_toward_the_players_record(self, service, repo, match_log):
        slug, bracket_id = published(service, repo, 4, name="Log Cup")
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        assert match_log.get_wins_count("u1") == 1
        assert match_log.get_losses_count("u4") == 1

    def test_undoing_a_result_takes_the_match_back(self, service, repo, match_db):
        slug, bracket_id = published(service, repo, 4, name="Log Cup")
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        service.reset_match(slug, match["match_no"])

        assert self._rows(match_db) == []
        assert repo.get_match(bracket_id, match["match_no"])["match_record_id"] is None

    def test_correcting_a_result_leaves_one_match_the_right_way_round(
        self, service, repo, match_db
    ):
        slug, bracket_id = published(service, repo, 4, name="Log Cup")
        match = repo.get_matches(bracket_id)[0]

        service.set_result(slug, match["match_no"], "u1", admin_id="a")
        service.set_result(slug, match["match_no"], "u4", admin_id="a")

        rows = self._rows(match_db)
        assert len(rows) == 1
        assert rows[0]["winner_id"] == "u4"

    def test_a_bye_is_not_a_played_match(self, service, repo, match_db):
        published(service, repo, 3, name="Bye Cup")
        assert self._rows(match_db) == []

    def test_each_result_is_logged_once(self, service, repo, match_db):
        slug, bracket_id = published(service, repo, 4, name="Log Cup")
        match = repo.get_matches(bracket_id)[0]

        service.set_result(slug, match["match_no"], "u1", admin_id="a")
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        assert len(self._rows(match_db)) == 1


class TestBracketGamesAreArchived:
    """Bracket games are filed in the match archive, never the running season."""

    def _add_events(self, elo_db, *events):
        import sqlite3

        conn = sqlite3.connect(str(elo_db))
        conn.executemany(
            "INSERT INTO events (event_id, event_name, start_date, end_date, is_active)"
            " VALUES (?, ?, ?, ?, ?)",
            events,
        )
        conn.commit()
        conn.close()

    def _table(self, match_db, table):
        import sqlite3

        conn = sqlite3.connect(str(match_db))
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(f"SELECT rowid AS row_id, * FROM {table}")]
        conn.close()
        return rows

    def test_a_result_goes_to_the_archive_only(self, service, repo, match_db):
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        assert self._table(match_db, "match_records") == []
        [row] = self._table(match_db, "match_records_archive")
        assert row["source"] == "Bracket"
        stored = repo.get_match(bracket_id, match["match_no"])
        assert stored["match_record_table"] == "match_records_archive"
        assert stored["match_record_id"] == row["row_id"]

    def test_it_is_filed_under_the_season_that_just_ended(
        self, service, repo, match_db, elo_db
    ):
        self._add_events(
            elo_db,
            (6, "Season 6", "2026-06-01", "2026-07-30", 0),
            (7, "Season 7", "2026-08-01", "2026-09-28", 0),
            (8, "Season 8", "2026-10-01", None, 1),
        )
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        [row] = self._table(match_db, "match_records_archive")
        assert row["event_id"] == 7

    def test_the_seeding_season_wins_once_it_has_ended(self, service, repo, match_db, elo_db):
        self._add_events(
            elo_db,
            (6, "Season 6", "2026-06-01", "2026-07-30", 0),
            (7, "Season 7", "2026-08-01", "2026-09-28", 0),
        )
        slug, bracket_id = published(service, repo, 4)
        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        conn.execute(
            "UPDATE brackets SET elo_event_name = 'Season 6' WHERE bracket_id = ?", (bracket_id,)
        )
        conn.commit()
        conn.close()
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        [row] = self._table(match_db, "match_records_archive")
        assert row["event_id"] == 6

    def test_resetting_removes_the_archived_game(self, service, repo, match_db):
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        service.reset_match(slug, match["match_no"])

        assert self._table(match_db, "match_records_archive") == []
        assert repo.get_match(bracket_id, match["match_no"])["match_record_table"] is None

    def test_it_still_counts_toward_the_players_record(self, service, repo, match_log):
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        assert match_log.get_wins_count("u1") == 1
        assert match_log.get_losses_count("u4") == 1

    def _season_logged(self, service, repo):
        """A game logged to match_records the way bracket games used to be."""
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")
        stored = repo.get_match(bracket_id, match["match_no"])
        service._match_repo.delete_match_row(
            stored["match_record_id"], table="match_records_archive"
        )
        row_id = service._match_repo.insert_match({
            "match_id": "m-1", "winner_id": "u1", "losser_id": "u4",
            "source": "Bracket", "timestamp": "2026-10-02 12:00:00",
            "match_comment": "Top cut game - Test Cup - Round 1",
        })
        repo.update_match(
            bracket_id, match["match_no"],
            {"match_record_id": row_id, "match_record_table": None},
        )
        return slug, bracket_id, match

    def test_games_already_in_the_season_are_moved_out(self, service, repo, match_db, elo_db):
        self._add_events(elo_db, (7, "Season 7", "2026-08-01", "2026-09-28", 0))
        _, bracket_id, match = self._season_logged(service, repo)

        assert service.archive_existing_records() == 1

        assert self._table(match_db, "match_records") == []
        [row] = self._table(match_db, "match_records_archive")
        assert (row["event_id"], row["source"]) == (7, "Bracket")
        assert row["original_match_id"] == "m-1"
        assert row["match_comment"].startswith("Top cut game")
        stored = repo.get_match(bracket_id, match["match_no"])
        assert (stored["match_record_id"], stored["match_record_table"]) == (
            row["row_id"], "match_records_archive"
        )

    def test_moving_is_done_once(self, service, repo, match_db):
        self._season_logged(service, repo)

        service.archive_existing_records()
        assert service.archive_existing_records() == 0
        assert len(self._table(match_db, "match_records_archive")) == 1

    def test_a_season_logged_game_can_still_be_reset(self, service, repo, match_db):
        slug, _, match = self._season_logged(service, repo)

        service.reset_match(slug, match["match_no"])

        assert self._table(match_db, "match_records") == []


class TestFinishes:
    """How far each entrant got, and what that finish is called."""

    def _play_out(self, service, repo, slug, bracket_id, winner_by_seed=True):
        """Settle every match; the better seed wins unless told otherwise."""
        for _ in range(64):
            detail = service.get_bracket_detail(slug)
            live = [
                m
                for r in detail["rounds"]
                for m in r["matches"]
                if m["playable"] and m["state"] in ("pending", "reported")
            ]
            if not live:
                return
            m = live[0]
            better = m["p1_user_id"] if m["p1_seed"] < m["p2_seed"] else m["p2_user_id"]
            worse = m["p2_user_id"] if m["p1_seed"] < m["p2_seed"] else m["p1_user_id"]
            service.set_result(slug, m["match_no"], better if winner_by_seed else worse, admin_id="a")

    def test_labels_by_placement(self):
        assert BracketService.finish_label(1) == "Champion"
        assert BracketService.finish_label(2) == "Finalist"
        assert BracketService.finish_label(3) == "Top 4"
        assert BracketService.finish_label(5) == "Top 8"
        assert BracketService.finish_label(9) == "Top cut"
        assert BracketService.finish_label(None) is None

    def test_an_eight_player_bracket_places_everyone(self, service, repo):
        slug, bracket_id = published(service, repo, 8, name="Finish Cup")
        self._play_out(service, repo, slug, bracket_id)

        placements = service.placements(bracket_id)
        assert placements[1] == 1        # seed 1 wins it
        assert placements[2] == 2        # loses the final
        assert sorted([placements[3], placements[4]]) == [3, 3]
        assert sorted(placements[s] for s in (5, 6, 7, 8)) == [5, 5, 5, 5]

    def test_a_player_still_in_has_no_placement_yet(self, service, repo):
        slug, bracket_id = published(service, repo, 8, name="Finish Cup")
        first = repo.get_matches(bracket_id)[0]
        service.set_result(slug, first["match_no"], "u1", admin_id="a")

        placements = service.placements(bracket_id)
        assert 8 in placements      # knocked out
        assert 1 not in placements  # still going

    def test_byes_do_not_place_anyone(self, service, repo):
        slug, bracket_id = published(service, repo, 5, name="Bye Finish")
        assert service.placements(bracket_id) == {}


class TestPlayerMarks:
    def _finished(self, service, repo, name="Marks Cup", size=8):
        slug, bracket_id = published(service, repo, size, name=name)
        for _ in range(64):
            detail = service.get_bracket_detail(slug)
            live = [
                m for r in detail["rounds"] for m in r["matches"]
                if m["playable"] and m["state"] == "pending"
            ]
            if not live:
                break
            m = live[0]
            better = m["p1_user_id"] if m["p1_seed"] < m["p2_seed"] else m["p2_user_id"]
            service.set_result(slug, m["match_no"], better, admin_id="a")
        return slug, bracket_id

    def test_marks_summarise_a_finished_bracket(self, service, repo):
        self._finished(service, repo)
        marks = service.get_player_marks()

        assert marks["u1"]["wins"] == 1
        assert marks["u1"]["best_label"] == "Champion"
        assert marks["u2"]["best_label"] == "Finalist"
        assert marks["u3"]["best_label"] == "Top 4"
        assert marks["u5"]["best_label"] == "Top 8"

    def test_a_bracket_still_running_earns_no_marks(self, service, repo):
        slug, bracket_id = published(service, repo, 8, name="Live Cup")
        first = repo.get_matches(bracket_id)[0]
        service.set_result(slug, first["match_no"], "u1", admin_id="a")

        assert service.get_player_marks() == {}

    def test_wins_stack_and_the_best_finish_is_kept(self, service, repo):
        self._finished(service, repo, name="Cup One")
        self._finished(service, repo, name="Cup Two")

        marks = service.get_player_marks()
        assert marks["u1"]["wins"] == 2
        assert len(marks["u1"]["entries"]) == 2
        # Two finalist finishes still read as one finalist.
        assert marks["u2"]["wins"] == 0
        assert marks["u2"]["best_label"] == "Finalist"


class TestPlayerPostseason:
    def test_it_lists_the_brackets_a_player_was_in(self, service, repo):
        slug, bracket_id = published(service, repo, 8, name="History Cup")
        first = repo.get_matches(bracket_id)[0]  # seed 1 v seed 8
        service.set_result(slug, first["match_no"], "u1", admin_id="a")

        entries = service.get_player_postseason("u1")
        assert len(entries) == 1
        assert entries[0]["name"] == "History Cup"
        assert entries[0]["seed"] == 1
        assert entries[0]["wins"] == 1
        assert entries[0]["label"] == "Still in"

    def test_a_knocked_out_player_shows_their_finish(self, service, repo):
        slug, bracket_id = published(service, repo, 8, name="History Cup")
        first = repo.get_matches(bracket_id)[0]
        service.set_result(slug, first["match_no"], "u1", admin_id="a")

        entry = service.get_player_postseason("u8")[0]
        assert entry["label"] == "Top 8"
        assert (entry["wins"], entry["losses"]) == (0, 1)

    def test_someone_who_never_entered_has_nothing(self, service, repo):
        published(service, repo, 8, name="History Cup")
        assert service.get_player_postseason("u99") == []


class TestBracketGamesAreNotSeasonGames:
    """A bracket is postseason: lifetime only, never the season standings."""

    SEASON_START = "2020-01-01 00:00:00"

    def _settle_one(self, service, repo):
        slug, bracket_id = published(service, repo, 4, name="Season Guard Cup")
        match = repo.get_matches(bracket_id)[0]  # seed 1 v seed 4
        service.set_result(slug, match["match_no"], "u1", admin_id="a")
        return slug, bracket_id

    def test_it_does_not_add_wins_to_the_season_record(self, service, repo, match_log):
        self._settle_one(service, repo)

        records = match_log.get_season_records(self.SEASON_START)
        assert "u1" not in records
        assert "u4" not in records

    def test_it_does_not_add_a_player_to_the_season(self, service, repo, match_log):
        self._settle_one(service, repo)
        assert "u1" not in [str(p) for p in match_log.get_season_players(self.SEASON_START)]

    def test_it_does_not_move_a_players_season_counts(self, service, repo, match_log):
        self._settle_one(service, repo)

        assert match_log.get_season_wins_count("u1", self.SEASON_START) == 0
        assert match_log.get_season_losses_count("u4", self.SEASON_START) == 0

    def test_it_still_counts_toward_the_lifetime_record(self, service, repo, match_log):
        self._settle_one(service, repo)

        assert match_log.get_wins_count("u1") == 1
        assert match_log.get_losses_count("u4") == 1

    def test_ordinary_games_still_count_for_the_season(self, service, repo, match_log, match_db):
        """The guard must only skip bracket games."""
        from tests.conftest import seed_matches

        seed_matches(match_db, [
            {
                "winner_id": "u1", "winner_name": "P1",
                "loser_id": "u4", "loser_name": "P4",
                "timestamp": "2026-01-02 12:00:00",
            }
        ])
        self._settle_one(service, repo)

        records = match_log.get_season_records(self.SEASON_START)
        assert records["u1"]["wins"] == 1   # the ordinary game, not the bracket one
        assert records["u4"]["losses"] == 1

    def test_the_event_ladder_number_is_untouched(self, service, repo, elo_db):
        import sqlite3

        self._settle_one(service, repo)
        conn = sqlite3.connect(str(elo_db))
        rows = dict(
            conn.execute(
                "SELECT user_id, online_event_elo FROM overall_standings "
                "WHERE user_id IN ('u1', 'u4')"
            )
        )
        conn.close()
        assert rows == {"u1": 1500, "u4": 1500}


class TestPlayersKeepTheirName:
    """A seeding records a name; it must not become the name of record.

    Players are seeded under whatever name the admin search returned, which
    for a Discord login is the handle they signed up with. If they have since
    set a display name, that is what the leaderboard and their profile show,
    and the bracket has to agree - and it must never write its own copy back
    over the ladder.
    """

    def test_the_bracket_shows_the_name_the_site_shows(self, service, repo, ladder):
        slug, _ = published(service, repo, 4)
        ladder.rename_player("u1", "Gwendolyn")

        detail = service.get_bracket_detail(slug)

        seed_one = next(e for e in detail["entrants"] if e["seed"] == 1)
        assert seed_one["display_name"] == "Gwendolyn"

    def test_a_pairing_shows_the_name_the_site_shows(self, service, repo, ladder):
        slug, _ = published(service, repo, 4)
        ladder.rename_player("u1", "Gwendolyn")

        detail = service.get_bracket_detail(slug)
        names = [
            match[f"p{slot}_name"]
            for round_data in detail["rounds"]
            for match in round_data["matches"]
            for slot in (1, 2)
        ]
        assert "Gwendolyn" in names
        assert "P1" not in names

    def test_the_champion_is_announced_under_it_too(self, service, repo, ladder):
        slug, bracket_id = published(service, repo, 2)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")
        ladder.rename_player("u1", "Gwendolyn")

        assert service.get_bracket_detail(slug)["champion"]["display_name"] == "Gwendolyn"
        listed = next(b for b in service.list_brackets() if b["slug"] == slug)
        assert listed["champion"]["display_name"] == "Gwendolyn"

    def test_the_deck_roster_uses_it(self, service, repo, ladder):
        slug, _ = published(service, repo, 4)
        ladder.rename_player("u2", "Gwendolyn")

        roster = service.get_deck_roster(slug, is_admin=True)
        assert "Gwendolyn" in [p["display_name"] for p in roster["players"]]

    def test_the_draft_preview_uses_it(self, service, repo, ladder):
        created = service.create_bracket(name="Preview Cup", size=4, source="overall")
        ladder.rename_player("u1", "Gwendolyn")

        preview = service.preview(created["bracket_id"])
        assert preview["entrants"][0]["display_name"] == "Gwendolyn"

    def test_settling_a_match_does_not_rename_anyone(self, service, repo, ladder):
        """The bug this guards: a result used to write the seeded name back."""
        slug, bracket_id = published(service, repo, 4)
        ladder.rename_player("u1", "Gwendolyn")
        ladder.rename_player("u4", "Count Tolstoy")

        match = repo.get_matches(bracket_id)[0]  # seed 1 v seed 4
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        names = ladder.get_display_names(["u1", "u4"])
        assert names == {"u1": "Gwendolyn", "u4": "Count Tolstoy"}

    def test_undoing_a_result_does_not_rename_anyone_either(self, service, repo, ladder):
        slug, bracket_id = published(service, repo, 4)
        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")
        ladder.rename_player("u1", "Gwendolyn")

        service.reset_match(slug, match["match_no"])

        assert ladder.get_display_names(["u1"]) == {"u1": "Gwendolyn"}

    def test_the_rating_stays_put(self, service, repo, ladder):
        slug, bracket_id = published(service, repo, 4)
        ladder.rename_player("u1", "Gwendolyn")

        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        assert ladder.get_user_elo("u1") == 1500
        assert ladder.get_user_elo("u4") == 1500

    def test_the_logged_match_uses_the_current_name(self, service, repo, ladder, match_db):
        import sqlite3

        slug, bracket_id = published(service, repo, 4)
        ladder.rename_player("u1", "Gwendolyn")

        match = repo.get_matches(bracket_id)[0]
        service.set_result(slug, match["match_no"], "u1", admin_id="a")

        conn = sqlite3.connect(str(match_db))
        row = conn.execute(
            "SELECT winner_display_name, losser_display_name FROM match_records_archive"
        ).fetchone()
        conn.close()
        assert row == ("Gwendolyn", "P4")

    def test_a_name_the_player_chose_beats_the_ladders(self, service, repo, ladder, match_db):
        """The profile honours a chosen display name; so does the bracket."""
        from repositories.user_profiles import UserProfileRepository
        import sqlite3

        profiles = UserProfileRepository(db_path=match_db)
        profiles.upsert_profile(user_id="u1", display_name="gwendabear", provider="discord")
        conn = sqlite3.connect(str(match_db))
        conn.execute(
            "UPDATE user_profiles SET custom_display_name = 'Gwendolyn' WHERE user_id = 'u1'"
        )
        conn.commit()
        conn.close()
        service._profile_repo_override = profiles

        slug, _ = published(service, repo, 4)
        detail = service.get_bracket_detail(slug)

        assert detail["entrants"][0]["display_name"] == "Gwendolyn"

    def test_a_google_account_is_found_by_its_bare_id(self, service, repo, match_db):
        """Profiles key Google users with a prefix the bot's tables do not."""
        from repositories.user_profiles import UserProfileRepository
        import sqlite3

        profiles = UserProfileRepository(db_path=match_db)
        profiles.upsert_profile(user_id="google_u2", display_name="u2@mail", provider="google")
        conn = sqlite3.connect(str(match_db))
        conn.execute(
            "UPDATE user_profiles SET custom_display_name = 'Count Tolstoy'"
            " WHERE user_id = 'google_u2'"
        )
        conn.commit()
        conn.close()

        assert profiles.get_custom_display_names(["u2"]) == {"u2": "Count Tolstoy"}

    def test_a_player_with_no_ladder_entry_keeps_their_seeded_name(self, service, repo):
        """An entrant added by hand may not be on the ladder at all."""
        created = service.create_bracket(name="Guest Cup", size=2, source="overall")
        service.set_entrants(created["bracket_id"], [
            {"user_id": "u1", "display_name": "P1"},
            {"user_id": "guest", "display_name": "A Guest"},
        ])
        service.publish(created["bracket_id"])

        detail = service.get_bracket_detail(created["slug"])
        assert [e["display_name"] for e in detail["entrants"]] == ["P1", "A Guest"]

    def test_a_broken_name_lookup_leaves_the_bracket_readable(self, service, repo):
        slug, _ = published(service, repo, 4)

        class Broken:
            def get_display_names(self, user_ids):
                raise RuntimeError("elo.db is away")

        service._elo_repo_override = Broken()
        detail = service.get_bracket_detail(slug)
        assert detail["entrants"][0]["display_name"] == "P1"


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

    def test_admin_swaps_players_in_a_published_bracket(self, admin_session, client):
        created = admin_session.post(
            "/api/admin/brackets", json={"name": "Swap Cup", "size": 2, "source": "overall"}
        ).get_json()
        slug = created["slug"]
        admin_session.post(f"/api/admin/brackets/{slug}/publish")

        # Two players are always opponents, so the only swap is refused.
        resp = admin_session.post(
            f"/api/admin/brackets/{slug}/swap", json={"seed": 1, "with_seed": 2}
        )
        assert resp.status_code == 400
        assert "playing each other" in resp.get_json()["error"]

        resp = admin_session.post(f"/api/admin/brackets/{slug}/swap", json={"seed": 1})
        assert resp.status_code == 400

        with client.session_transaction() as sess:
            sess["user_id"] = "p_one"
        resp = client.post(f"/api/admin/brackets/{slug}/swap", json={"seed": 1, "with_seed": 2})
        assert resp.status_code in (401, 403)

    def test_admin_adds_a_finished_bracket_to_the_top8_page(self, admin_session, events_dir):
        created = admin_session.post(
            "/api/admin/brackets", json={"name": "Top Cup", "size": 2, "source": "overall"}
        ).get_json()
        slug = created["slug"]
        admin_session.post(f"/api/admin/brackets/{slug}/publish")

        resp = admin_session.post(f"/api/admin/brackets/{slug}/top8")
        assert resp.status_code == 400
        assert "finished" in resp.get_json()["error"]

        admin_session.post(
            f"/api/admin/brackets/{slug}/matches/1/result", json={"winner_user_id": "p_one"}
        )
        # Nobody filed a deck, so finishing had nothing to publish.
        resp = admin_session.post(f"/api/admin/brackets/{slug}/top8")
        assert resp.status_code == 400
        assert "decklist" in resp.get_json()["error"]
        assert not any(events_dir.iterdir())

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

    def test_preview_endpoint_is_admin_only(self, admin_session, app):
        created = admin_session.post(
            "/api/admin/brackets", json={"name": "Preview", "size": 2, "source": "overall"}
        ).get_json()

        anonymous = app.test_client()
        assert anonymous.get(
            f"/api/admin/brackets/{created['slug']}/preview"
        ).status_code in (401, 403)

        preview = admin_session.get(f"/api/admin/brackets/{created['slug']}/preview").get_json()
        assert preview["bracket_size"] == 2
        assert preview["rounds"][0]["title"] == "Finals"

    def test_opening_a_table_requires_login(self, admin_session, app):
        slug = self._create_and_publish(admin_session)
        anonymous = app.test_client()
        assert anonymous.post(
            f"/api/brackets/{slug}/matches/1/table"
        ).status_code in (401, 403)

    def test_replay_endpoints_require_admin(self, admin_session, app):
        slug = self._create_and_publish(admin_session)
        anonymous = app.test_client()
        assert anonymous.post(
            f"/api/admin/brackets/{slug}/matches/1/replay",
            json={"replay_url": "https://playsorceryonline.com/replay/a"},
        ).status_code in (401, 403)

    def test_admin_attaches_and_removes_a_replay(self, admin_session):
        slug = self._create_and_publish(admin_session)
        admin_session.post(
            f"/api/admin/brackets/{slug}/matches/1/result", json={"winner_user_id": "p_one"}
        )

        resp = admin_session.post(
            f"/api/admin/brackets/{slug}/matches/1/replay",
            json={"replay_url": "https://playsorceryonline.com/replay/abc"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["public"] is True  # a 2-player bracket is now complete

        detail = admin_session.get(f"/api/brackets/{slug}").get_json()
        assert detail["rounds"][0]["matches"][0]["replay_url"].endswith("/replay/abc")

        assert admin_session.delete(
            f"/api/admin/brackets/{slug}/matches/1/replay"
        ).status_code == 200
        assert admin_session.delete(
            f"/api/admin/brackets/{slug}/matches/1/replay"
        ).status_code == 404

    def test_a_replay_link_from_elsewhere_is_refused(self, admin_session):
        slug = self._create_and_publish(admin_session)
        resp = admin_session.post(
            f"/api/admin/brackets/{slug}/matches/1/replay",
            json={"replay_url": "https://example.com/not-a-replay"},
        )
        assert resp.status_code == 400

    def test_a_pso_report_for_a_bracket_table_is_acknowledged(self, admin_session, app):
        """PSO echoes our pairing id; the bracket is the record, so do not fail it."""
        slug = self._create_and_publish(admin_session)
        bracket = admin_session.get(f"/api/admin/brackets/{slug}").get_json()
        bracket_id = bracket["bracket"]["bracket_id"]

        reporter = app.test_client()
        resp = reporter.post(
            "/api/report-external-match",
            headers={"X-API-Key": "test-api-key-123"},
            json={
                "winner_id": "p_one",
                "loser_id": "p_two",
                "winner_deck_url": "https://curiosa.io/decks/a",
                "loser_deck_url": "https://curiosa.io/decks/b",
                "source": "PSO Ranked",
                "pairing_id": f"bracket-{bracket_id}-m1",
            },
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["pipeline"] == "bracket"
        assert body["bracket_slug"] == slug
        assert body["state"] == "reported"

        # The table's winner waits on the bracket for the players to confirm.
        match = admin_session.get(f"/api/brackets/{slug}").get_json()["rounds"][0]["matches"][0]
        assert match["state"] == "reported"
        assert match["reported_winner_id"] == "p_one"

    def _report(self, app, **overrides):
        payload = {
            "winner_id": "p_one",
            "loser_id": "p_two",
            "winner_deck_url": "https://curiosa.io/decks/a",
            "loser_deck_url": "https://curiosa.io/decks/b",
            "source": "PSO Ranked",
        }
        payload.update(overrides)
        return app.test_client().post(
            "/api/report-external-match",
            headers={"X-API-Key": "test-api-key-123"},
            json=payload,
        )

    def _open_table(self, admin_session, slug):
        from repositories.brackets import BracketRepository

        bracket_id = admin_session.get(f"/api/admin/brackets/{slug}").get_json()["bracket"][
            "bracket_id"
        ]
        BracketRepository().update_match(
            bracket_id, 1, {"table_provisioned_at": "2026-10-03T12:00:00"}
        )
        return bracket_id

    def test_a_bracket_table_report_without_a_pairing_id_is_never_rated(
        self, admin_session, app
    ):
        """PSO may drop our pairing id; the open table still marks it top cut."""
        from unittest.mock import patch

        slug = self._create_and_publish(admin_session)
        self._open_table(admin_session, slug)

        with patch("routes.api.external_matches._record_pso_ranked") as ranked:
            resp = self._report(app)

        assert resp.status_code == 200
        assert resp.get_json()["pipeline"] == "bracket"
        ranked.assert_not_called()

    def test_the_bracket_pairing_id_is_found_under_other_keys(self, admin_session, app):
        from unittest.mock import patch

        slug = self._create_and_publish(admin_session)
        bracket_id = self._open_table(admin_session, slug)

        with patch("routes.api.external_matches._record_pso_ranked") as ranked:
            resp = self._report(app, matchId=f"summit:bracket-{bracket_id}-m1")

        assert resp.get_json()["pipeline"] == "bracket"
        ranked.assert_not_called()

    def test_players_without_a_bracket_table_still_play_ranked(self, admin_session, app):
        from unittest.mock import patch

        self._create_and_publish(admin_session)  # no table opened

        with patch("routes.api.external_matches._record_pso_ranked") as ranked:
            ranked.return_value = ({"pipeline": "pso_ranked"}, 200)
            self._report(app)

        ranked.assert_called_once()

    def test_a_bracket_report_naming_the_wrong_players_is_refused(self, admin_session, app):
        slug = self._create_and_publish(admin_session)
        bracket_id = admin_session.get(f"/api/admin/brackets/{slug}").get_json()["bracket"][
            "bracket_id"
        ]

        reporter = app.test_client()
        resp = reporter.post(
            "/api/report-external-match",
            headers={"X-API-Key": "test-api-key-123"},
            json={
                "winner_id": "someone",
                "loser_id": "else",
                "winner_deck_url": "https://curiosa.io/decks/a",
                "loser_deck_url": "https://curiosa.io/decks/b",
                "source": "PSO Ranked",
                "pairing_id": f"bracket-{bracket_id}-m1",
            },
        )
        assert resp.status_code == 400

    def test_delete(self, admin_session):
        slug = self._create_and_publish(admin_session)
        assert admin_session.delete(f"/api/admin/brackets/{slug}").status_code == 200
        assert admin_session.delete(f"/api/admin/brackets/{slug}").status_code == 404


# -- Card set grouping --------------------------------------------


class TestSetName:
    def test_a_bracket_is_created_with_its_set(self, service, repo):
        created = service.create_bracket(
            name="Spring Cup", size=4, source="overall", set_name="  Gothic  "
        )
        assert repo.get_bracket(bracket_id=created["bracket_id"])["set_name"] == "Gothic"

    def test_a_blank_set_is_stored_as_none(self, service, repo):
        created = service.create_bracket(name="Spring Cup", size=4, source="overall", set_name=" ")
        assert repo.get_bracket(bracket_id=created["bracket_id"])["set_name"] is None

    def test_the_set_can_be_changed_and_cleared(self, service, repo):
        created = service.create_bracket(name="Spring Cup", size=4, source="overall")
        bracket_id = created["bracket_id"]

        assert service.update_bracket(bracket_id, {"set_name": "Arthurian   Legends"})
        assert repo.get_bracket(bracket_id=bracket_id)["set_name"] == "Arthurian Legends"

        assert service.update_bracket(bracket_id, {"set_name": ""})
        assert repo.get_bracket(bracket_id=bracket_id)["set_name"] is None

    def test_the_set_travels_with_the_public_list(self, service, repo):
        published(service, repo, count=4, name="Gothic Season 1")
        bracket = service.list_brackets()[0]
        assert "set_name" in bracket

    def test_existing_gothic_brackets_are_tagged_when_the_column_arrives(self, tmp_path):
        import sqlite3

        from migrations.create_bracket_tables import create_bracket_tables

        db = tmp_path / "old.db"
        conn = sqlite3.connect(db)
        conn.execute(
            """CREATE TABLE brackets (
                bracket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, description TEXT,
                entrant_count INTEGER NOT NULL, bracket_size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft', seeded_from TEXT,
                elo_event_name TEXT, confirm_hours INTEGER NOT NULL DEFAULT 48,
                created_by TEXT, created_at TEXT NOT NULL, published_at TEXT,
                completed_at TEXT, updated_at TEXT
            )"""
        )
        for slug, name in (("g1", "Gothic Season 1 Top Cut"), ("x", "Summer Open")):
            conn.execute(
                "INSERT INTO brackets (slug, name, entrant_count, bracket_size, created_at)"
                " VALUES (?, ?, 8, 8, 'now')",
                (slug, name),
            )
        conn.commit()
        conn.close()

        create_bracket_tables(db)
        conn = sqlite3.connect(db)
        tagged = dict(conn.execute("SELECT slug, set_name FROM brackets").fetchall())
        assert tagged == {"g1": "Gothic", "x": None}

        # A second run must not re-tag a bracket the admin has since cleared.
        conn.execute("UPDATE brackets SET set_name = NULL WHERE slug = 'g1'")
        conn.commit()
        conn.close()
        create_bracket_tables(db)

        conn = sqlite3.connect(db)
        rows = dict(conn.execute("SELECT slug, set_name FROM brackets").fetchall())
        conn.close()
        assert rows == {"g1": None, "x": None}


class TestSetNameApi:
    @pytest.fixture(autouse=True)
    def _seed_players(self, elo_db):
        seed_elo_data(elo_db, [
            {"user_id": "p_one", "name": "One", "online_event_elo": 1900},
            {"user_id": "p_two", "name": "Two", "online_event_elo": 1800},
        ])

    def test_create_and_patch_the_set(self, admin_session):
        created = admin_session.post(
            "/api/admin/brackets",
            json={"name": "Set Cup", "size": 2, "source": "overall", "set_name": "Gothic"},
        ).get_json()
        slug = created["slug"]
        detail = admin_session.get(f"/api/admin/brackets/{slug}").get_json()
        assert detail["bracket"]["set_name"] == "Gothic"

        resp = admin_session.patch(f"/api/admin/brackets/{slug}", json={"set_name": "Beta"})
        assert resp.status_code == 200
        detail = admin_session.get(f"/api/admin/brackets/{slug}").get_json()
        assert detail["bracket"]["set_name"] == "Beta"
