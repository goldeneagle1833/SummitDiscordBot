"""Meta Report: periods, numbers, publishing and email sign-up."""

import json
import sqlite3
import uuid
from datetime import date

import pytest

from repositories.meta_reports import MetaReportRepository
from services import meta_report
from services.meta_report import Period


def deck(avatar, element, n=40):
    return json.dumps({
        "avatar": [{"name": avatar}],
        "spellbook": [{"name": f"{element} card", "quantity": n, "elements": element}],
    })


def add_game(db, day, winner, loser, match_type="ranked", match_id=None):
    conn = sqlite3.connect(str(db))
    conn.execute(
        """INSERT INTO match_records (match_id, timestamp, json_deck_data_winner,
           json_deck_data_loser, match_type, winner_display_name, losser_display_name)
           VALUES (?, ?, ?, ?, ?, 'secret winner', 'secret loser')""",
        (match_id or uuid.uuid4().hex, f"{day}T12:00:00",
         deck(*winner), deck(*loser), match_type),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def repo(tmp_path):
    return MetaReportRepository(tmp_path / "meta.db")


@pytest.fixture()
def no_events(monkeypatch):
    monkeypatch.setattr(meta_report, "tournament_section",
                        lambda f, t, a: {"events": [], "deckToTry": None})


# ---------------------------------------------------------------- periods

def test_periods_lag_one_month():
    assert Period(2026, 9, "a").publish_day == date(2026, 10, 1)
    assert Period(2026, 9, "b").publish_day == date(2026, 10, 16)
    assert Period(2026, 12, "b").publish_day == date(2027, 1, 16)
    assert Period(2026, 2, "b").end == date(2026, 2, 28)


def test_latest_due_period():
    # Oct 1-15 shows Sep 1-15; Oct 16 onward shows Sep 16-30.
    assert latest(date(2026, 10, 1)) == "2026-09-a"
    assert latest(date(2026, 10, 15)) == "2026-09-a"
    assert latest(date(2026, 10, 16)) == "2026-09-b"
    assert latest(date(2026, 1, 3)) == "2025-12-a"


def latest(day):
    return meta_report.latest_due_period(day).slug


def test_period_slug_round_trip_and_validation():
    assert Period.from_slug("2026-09-b").label() == "Sep 16–30, 2026"
    assert Period(2026, 1, "a").previous().slug == "2025-12-b"
    for bad in ("2026-13-a", "2026-09-c", "nope", ""):
        with pytest.raises(ValueError):
            Period.from_slug(bad)


# ---------------------------------------------------------------- ranked numbers

def test_ranked_games_stay_in_period_and_ranked_only(match_db):
    add_game(match_db, "2026-09-02", ("Sparkmage", "Air"), ("Geomancer", "Earth"))
    add_game(match_db, "2026-09-20", ("Sparkmage", "Air"), ("Geomancer", "Earth"))
    add_game(match_db, "2026-09-03", ("Sparkmage", "Air"), ("Geomancer", "Earth"), match_type="casual")
    games = meta_report.ranked_games("2026-09-01", "2026-09-15", match_db)
    assert games == [{"winner": ("Sparkmage", "Air"), "loser": ("Geomancer", "Earth")}]


def test_archetype_stats_tiers_and_minimums():
    games = (
        [{"winner": ("A", "Fire"), "loser": ("B", "Water")}] * 30
        + [{"winner": ("B", "Water"), "loser": ("C", "Earth")}] * 12
        + [{"winner": ("D", "Air"), "loser": None}] * 3  # under the minimum
    )
    stats = meta_report.archetype_stats(games)
    names = [a["avatar"] for a in stats["archetypes"]]
    assert names[0] == "A" and "D" not in names
    top = stats["archetypes"][0]
    assert top["tier"] == "S" and top["winRate"] == 100.0
    assert stats["rankedGames"] == 45


def test_matchups_are_avatar_against_avatar():
    games = [{"winner": ("A", "Fire"), "loser": ("B", "Water")}] * 6 + \
            [{"winner": ("A", "Air"), "loser": ("B", "Earth")}] * 3 + \
            [{"winner": ("B", "Water"), "loser": ("A", "Fire")}] * 6
    grid = meta_report.matchup_grid(games)
    a = [x["avatar"] for x in grid["archetypes"]].index("A")
    b = 1 - a
    assert grid["cells"][a][a] is None
    assert grid["cells"][a][b] == {"games": 15, "winRate": 60.0}
    few = meta_report.matchup_grid(games[:6])
    assert few["cells"][a][b]["winRate"] is None


def test_tier_moves_against_previous_period():
    current = [{"avatar": "A", "elements": "Fire", "tier": "S"}, {"avatar": "B", "elements": "Water", "tier": "C"}]
    previous = [{"avatar": "A", "elements": "Fire", "tier": "B"}]
    meta_report._with_moves(current, previous)
    assert current[0]["move"] == 2 and current[1]["move"] == "new"


# ---------------------------------------------------------------- PSO cards

def rate(games, wr):
    return {"playerGames": games, "matches": games, "wins": None, "winRate": wr}


def cards_body(rows, released="2026-09-15"):
    return {"dataAvailable": True, "releasedThrough": released, "totalGames": 500,
            "cards": [{"cardKey": k, "cardName": k.title(), "deckShare": s, "played": rate(g, wr)}
                      for k, s, g, wr in rows]}


def test_card_section_movers_and_sleeper():
    now = cards_body([("bolt", 0.40, 300, 0.55), ("trolls", 0.10, 120, 0.48), ("pixies", 0.05, 80, 0.62)])
    before = cards_body([("bolt", 0.30, 200, 0.52), ("trolls", 0.20, 150, 0.50), ("pixies", 0.05, 60, 0.60)])
    section = meta_report.card_section(now, before, [], "2026-09-15")
    assert section["rising"][0]["name"] == "Bolt" and section["rising"][0]["change"] == 10.0
    assert section["falling"][0]["name"] == "Trolls"
    assert section["sleeper"]["name"] == "Pixies"


def test_card_section_without_earlier_period_shows_top_cards():
    now = cards_body([("bolt", 0.40, 300, 0.55), ("pixies", 0.05, 80, 0.62), ("rare", 0.01, 5, 0.9)])
    section = meta_report.card_section(now, None, [], "2026-09-15")
    assert section["mode"] == "top"
    assert [c["name"] for c in section["rising"]][:2] == ["Bolt", "Pixies"]
    assert [c["name"] for c in section["falling"]] == ["Pixies", "Bolt"]


def test_card_section_with_no_rows_is_unavailable():
    assert meta_report.card_section(cards_body([]), None, [], "2026-09-15")["available"] is False


def test_card_section_waits_for_release():
    body = cards_body([("bolt", 0.4, 300, 0.55)], released="2026-09-10")
    assert meta_report.card_section(body, None, [], "2026-09-15")["available"] is False
    assert meta_report.card_section(None, None, [], "2026-09-15") == {"available": False}


# ---------------------------------------------------------------- build + publish

def test_build_never_includes_ranked_player_names(match_db, repo, no_events):
    for _ in range(25):
        add_game(match_db, "2026-09-05", ("Sparkmage", "Air"), ("Geomancer", "Earth"))
    report = meta_report.build(Period(2026, 9, "a"), repo, db_path=match_db, pso=lambda f, t: None)
    assert report["status"] == "draft"
    assert "secret" not in json.dumps(report)
    assert report["story"][0]["headline"].startswith("Sparkmage is the deck to beat")


def test_rebuild_keeps_edited_story(match_db, repo, no_events):
    period = Period(2026, 9, "a")
    meta_report.build(period, repo, db_path=match_db, pso=lambda f, t: None)
    repo.update_story(period.slug, [{"headline": "Edited", "detail": ""}])
    report = meta_report.build(period, repo, db_path=match_db, pso=lambda f, t: None)
    assert report["story"] == [{"headline": "Edited", "detail": ""}]


def test_publish_announces_once(match_db, repo, no_events, monkeypatch):
    calls = {"discord": 0, "banner": 0}
    monkeypatch.setattr(meta_report, "post_to_discord", lambda r: calls.__setitem__("discord", calls["discord"] + 1) or True)
    monkeypatch.setattr(meta_report, "create_banner", lambda r: calls.__setitem__("banner", calls["banner"] + 1))
    sub = repo.add_subscriber("fan@example.com")
    repo.confirm(sub["token"])
    period = Period(2026, 9, "a")
    meta_report.build(period, repo, db_path=match_db, pso=lambda f, t: None)
    report = meta_report.publish(period.slug, "admin", repo=repo)
    assert report["status"] == "published" and report["discordPostedAt"] and report["bannerCreatedAt"]
    assert repo.email_counts(report["id"]) == {"pending": 1}
    meta_report.deliver(repo.get(period.slug), repo)
    assert calls == {"discord": 1, "banner": 1}
    assert repo.queue_report_emails(report["id"]) == 0


def test_quiet_publish_sends_nothing(match_db, repo, no_events, monkeypatch):
    monkeypatch.setattr(meta_report, "post_to_discord", lambda r: pytest.fail("posted"))
    period = Period(2026, 8, "b")
    meta_report.build(period, repo, db_path=match_db, pso=lambda f, t: None)
    report = meta_report.publish(period.slug, "admin", announce=False, repo=repo)
    assert report["status"] == "published" and not report["discordPostedAt"]
    assert repo.undelivered() == []


def test_failed_discord_post_is_retried(match_db, repo, no_events, monkeypatch):
    monkeypatch.setattr(meta_report, "create_banner", lambda r: None)
    monkeypatch.setattr(meta_report, "post_to_discord", lambda r: False)
    period = Period(2026, 9, "a")
    meta_report.build(period, repo, db_path=match_db, pso=lambda f, t: None)
    meta_report.publish(period.slug, "admin", repo=repo)
    assert [r["slug"] for r in repo.undelivered()] == [period.slug]


def test_auto_publish_waits_for_pso_then_publishes(repo, monkeypatch):
    built = []
    monkeypatch.setattr(meta_report, "build", lambda p, r: built.append(p.slug) or r.save_build(
        p.slug, p.start.isoformat(), p.end.isoformat(), {}, []))
    monkeypatch.setattr(meta_report, "deliver", lambda r, repo=None: {})
    assert meta_report.auto_publish_due(date(2026, 10, 1), repo, pso_ready=lambda p: False) is None
    assert built == []
    report = meta_report.auto_publish_due(date(2026, 10, 1), repo, pso_ready=lambda p: True)
    assert report["status"] == "published" and report["publishedBy"] == "auto"
    # Already made: nothing more happens.
    assert meta_report.auto_publish_due(date(2026, 10, 2), repo, pso_ready=lambda p: True) is None


def test_auto_publish_gives_up_waiting_and_skips_stale_periods(repo, monkeypatch):
    monkeypatch.setattr(meta_report, "build", lambda p, r: r.save_build(
        p.slug, p.start.isoformat(), p.end.isoformat(), {}, []))
    monkeypatch.setattr(meta_report, "deliver", lambda r, repo=None: {})
    # Eleven days past Oct 1: too late to announce on its own.
    assert meta_report.auto_publish_due(date(2026, 10, 12), repo, pso_ready=lambda p: True) is None
    # Three days after Oct 16 with no PSO data: publish anyway.
    report = meta_report.auto_publish_due(date(2026, 10, 19), repo, pso_ready=lambda p: False)
    assert report["slug"] == "2026-09-b"


# ---------------------------------------------------------------- subscribers

def test_subscriber_confirm_and_unsubscribe(repo):
    sub = repo.add_subscriber("Fan@Example.com")
    assert sub["confirmed_at"] is None
    repo.confirm(sub["token"])
    assert repo.subscriber_counts()["active"] == 1
    repo.unsubscribe(sub["token"])
    assert repo.subscriber_counts() == {"active": 0, "unconfirmed": 0, "unsubscribed": 1}
    again = repo.add_subscriber("fan@example.com")
    assert again["token"] != sub["token"] and again["confirmed_at"] is None


def test_report_email_has_unsubscribe_link(repo):
    report = {"slug": "2026-09-a", "story": [{"headline": "Big news", "detail": "Details."}],
              "payload": {"period": {"label": "Sep 1–15, 2026"}}}
    subject, text, html = meta_report.report_email(report, "tok123")
    assert "Sep 1–15" in subject
    assert "unsubscribe=tok123" in text and "unsubscribe=tok123" in html


# ---------------------------------------------------------------- routes

@pytest.fixture()
def api_repo(tmp_path, monkeypatch):
    path = tmp_path / "meta_reports.db"
    monkeypatch.setattr("repositories.meta_reports.META_REPORTS_DB_PATH", path)
    return MetaReportRepository(path)


def test_public_routes_hide_drafts(client, api_repo):
    api_repo.save_build("2026-09-a", "2026-09-01", "2026-09-15",
                        {"period": {"label": "Sep 1–15, 2026"}, "cards": {"available": True, "index": {"x": [1, 2]}}}, [])
    assert client.get("/api/meta-reports/2026-09-a").status_code == 404
    assert client.get("/api/meta-reports").get_json()["reports"] == []
    api_repo.publish("2026-09-a", "admin", announce=False)
    body = client.get("/api/meta-reports/2026-09-a").get_json()
    assert body["slug"] == "2026-09-a" and "index" not in body["cards"]
    assert client.get("/api/meta-reports").get_json()["reports"][0]["label"] == "Sep 1–15, 2026"


def test_admin_routes_need_admin(client, user_session, api_repo):
    assert user_session.get("/api/meta-reports/admin").status_code == 403
    assert user_session.post("/api/meta-reports/admin/build", json={"period": "2026-09-a"}).status_code == 403


def test_admin_can_edit_story(admin_session, api_repo):
    api_repo.save_build("2026-09-a", "2026-09-01", "2026-09-15", {}, [])
    res = admin_session.put("/api/meta-reports/admin/2026-09-a/story",
                            json={"story": [{"headline": " New take ", "detail": "x"}, {"headline": ""}]})
    assert res.get_json()["story"] == [{"headline": "New take", "detail": "x"}]
    listing = admin_session.get("/api/meta-reports/admin").get_json()
    assert listing["reports"][0]["slug"] == "2026-09-a" and len(listing["periods"]) == 12


def test_admin_cannot_build_future_period(admin_session, api_repo):
    res = admin_session.post("/api/meta-reports/admin/build", json={"period": "2099-01-a"})
    assert res.status_code == 400


def test_subscribe_validates_and_sends_confirmation(client, api_repo, monkeypatch):
    sent = []
    monkeypatch.setattr(meta_report, "email_configured", lambda: True)
    monkeypatch.setattr(meta_report, "send_confirmation", lambda sub: sent.append(sub["email"]) or True)
    assert client.post("/api/meta-reports/subscribe", json={"email": "nope"}).status_code == 400
    res = client.post("/api/meta-reports/subscribe", json={"email": "fan@example.com"})
    assert res.get_json() == {"status": "confirm_sent"} and sent == ["fan@example.com"]
    token = api_repo.add_subscriber("fan@example.com")["token"]
    assert client.post("/api/meta-reports/email/confirm", json={"token": token}).get_json() == {"status": "subscribed"}
    assert client.post("/api/meta-reports/email/unsubscribe", json={"token": token}).get_json() == {"status": "unsubscribed"}
    assert client.post("/api/meta-reports/email/confirm", json={"token": "x" * 20}).status_code == 404


def test_tournament_section_picks_deck_from_climbing_archetype(monkeypatch):
    class FakeEvents:
        def get_all_events(self):
            return [
                {"folder": "cup", "name": "Cup", "event_date": "2026-09-10", "player_count": 20,
                 "rating": 3, "winner_username": "Ann", "winner_avatar": "Sparkmage"},
                {"folder": "old", "name": "Old", "event_date": "2026-08-01", "player_count": 9},
            ]

        def get_event_decks(self, folder):
            return {"top8_decks": [
                {"player": "Ann", "avatar": "Sparkmage", "deck_id": "spark123", "elements": ["Fire", "Air"]},
                {"player": "Bo", "avatar": "Geomancer", "deck_id": "geo12345", "elements": ["Earth"]},
            ]}

    monkeypatch.setattr("repositories.events.EventRepository", FakeEvents)
    arch = [{"avatar": "Sparkmage", "elements": "Air / Fire", "tier": "A", "move": 0},
            {"avatar": "Geomancer", "elements": "Earth", "tier": "B", "move": 2}]
    section = meta_report.tournament_section("2026-09-01", "2026-09-15", arch)
    assert [e["name"] for e in section["events"]] == ["Cup"]
    assert section["events"][0]["winnerElements"] == "Air / Fire"
    assert section["deckToTry"]["deckId"] == "geo12345" and section["deckToTry"]["placement"] == 2


def test_og_preview_shows_headline_to_link_bots(client, api_repo):
    api_repo.save_build("2026-09-a", "2026-09-01", "2026-09-15", {},
                        [{"headline": "Sparkmage is the deck to beat.", "detail": ""}])
    api_repo.publish("2026-09-a", "admin", announce=False)
    res = client.get("/meta-report/2026-09-a", headers={"User-Agent": "Discordbot/2.0"})
    html = res.get_data(as_text=True)
    assert "Meta Report: Sep 1–15, 2026" in html and "Sparkmage is the deck to beat." in html
    latest = client.get("/meta-report", headers={"User-Agent": "Discordbot/2.0"}).get_data(as_text=True)
    assert "/meta-report/2026-09-a" in latest


def test_fragmented_meta_keeps_tiers_small():
    games = []
    for i in range(30):
        games += [{"winner": (f"Av{i}", "Fire"), "loser": (f"Av{(i + 1) % 30}", "Fire")}] * (20 + i)
    stats = meta_report.archetype_stats(games)
    tiers = [a["tier"] for a in stats["archetypes"]]
    assert tiers.count("S") <= 4 and tiers.count("A") <= 8


def test_tiny_archetypes_are_left_out():
    games = [{"winner": ("Big", "Fire"), "loser": ("Big2", "Water")}] * 200 + \
            [{"winner": ("Tiny", "Air"), "loser": None}] * 15
    names = [a["avatar"] for a in meta_report.archetype_stats(games)["archetypes"]]
    assert "Tiny" not in names and "Big" in names


def test_tiers_group_by_avatar_only():
    games = [{"winner": ("Imposter", "Air / Water"), "loser": ("Druid", "Air / Water")}] * 15 + \
            [{"winner": ("Imposter", "Air / Earth"), "loser": ("Druid", "Water")}] * 15
    rows = meta_report.archetype_stats(games)["archetypes"]
    assert [(a["avatar"], a["elements"], a["games"]) for a in rows] == [("Imposter", "", 30), ("Druid", "", 30)]


def test_best_win_rate_and_sleeper_skip_losing_cards():
    now = cards_body([("toolbox", 0.71, 40, 0.469), ("grapple", 0.56, 25, 0.56), ("odd", 0.04, 22, 0.45)])
    section = meta_report.card_section(now, None, [], "2026-09-15")
    assert [c["name"] for c in section["falling"]] == ["Grapple"]
    assert section["sleeper"] is None


def test_movers_use_saved_previous_report_when_pso_has_no_earlier_data(match_db, repo, no_events):
    before = cards_body([("bolt", 0.30, 100, 0.55), ("trolls", 0.20, 80, 0.50)])
    meta_report.build(Period(2026, 8, "b"), repo, db_path=match_db, pso=lambda f, t: before)
    now = cards_body([("bolt", 0.40, 100, 0.56), ("trolls", 0.10, 80, 0.48)])
    report = meta_report.build(Period(2026, 9, "a"), repo, db_path=match_db,
                               pso=lambda f, t: now if f == "2026-09-01" else None)
    cards = report["payload"]["cards"]
    assert cards["mode"] == "movers"
    assert [c["name"] for c in cards["rising"]] == ["Bolt"]
    assert [c["name"] for c in cards["falling"]] == ["Trolls"]
    assert cards["rising"][0]["trend"] == [55.0, 56.0]
