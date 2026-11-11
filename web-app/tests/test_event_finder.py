"""Find a player at an in-person event: hours window, privacy, API."""

from datetime import datetime, timezone

import pytest

from services import event_finder as rules

BOSTON_MAP = {
    "id": 1, "name": "Avatar of the Realm", "image_url": None,
    "start_date": "2026-11-13", "end_date": "2026-11-15",
    "daily_start": "08:00", "daily_end": "20:00",
    "timezone": "America/New_York", "spots": [],
}


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class TestWindow:
    # Boston is UTC-5 in November: 08:00 local = 13:00 UTC, 20:00 = 01:00 next day
    @pytest.mark.parametrize("when,reason", [
        (_utc(2026, 11, 12, 18, 0), "before"),
        (_utc(2026, 11, 13, 12, 59), "closed_today"),   # 7:59 a.m. Friday
        (_utc(2026, 11, 13, 13, 0), "open"),            # 8:00 a.m. Friday
        (_utc(2026, 11, 14, 0, 59), "open"),            # 7:59 p.m. Friday
        (_utc(2026, 11, 14, 1, 0), "closed_today"),     # 8:00 p.m. Friday
        (_utc(2026, 11, 15, 20, 0), "open"),            # 3 p.m. Sunday
        (_utc(2026, 11, 16, 1, 0), "after"),            # 8 p.m. Sunday, done
        (_utc(2026, 11, 17, 15, 0), "after"),
    ])
    def test_hours_follow_the_venue_clock(self, when, reason):
        status = rules.window_status(BOSTON_MAP, when)
        assert status["reason"] == reason
        assert status["open"] is (reason == "open")

    def test_no_map_is_closed(self):
        assert rules.window_status(None)["open"] is False


class TestPublicPerson:
    share = {"username": "Bruce", "sharing": 1, "x": 40.0, "y": 60.0,
             "label": "Summit booth", "note": "Ask for Bruce", "updated_at": "2026-11-13T15:00:00Z"}

    def test_spot_shown_during_hours(self):
        p = rules.public_person(self.share, BOSTON_MAP, _utc(2026, 11, 13, 15, 0))
        assert p["live"] is True
        assert (p["x"], p["y"], p["label"]) == (40.0, 60.0, "Summit booth")

    def test_spot_hidden_after_hours(self):
        p = rules.public_person(self.share, BOSTON_MAP, _utc(2026, 11, 14, 2, 0))
        assert p["live"] is False
        assert "x" not in p and "label" not in p and "note" not in p

    def test_spot_hidden_when_sharing_off(self):
        p = rules.public_person({**self.share, "sharing": 0}, BOSTON_MAP, _utc(2026, 11, 13, 15, 0))
        assert p["live"] is False and p["reason"] == "off"
        assert "x" not in p


class TestValidation:
    def test_share_needs_both_coordinates(self):
        with pytest.raises(ValueError):
            rules.clean_share_fields({"x": 10})
        assert rules.clean_share_fields({"x": None, "y": None}) == {"x": None, "y": None}

    def test_position_must_be_on_map(self):
        with pytest.raises(ValueError):
            rules.clean_share_fields({"x": 120, "y": 5})

    def test_map_dates_and_hours(self):
        with pytest.raises(ValueError):
            rules.clean_map_fields({"name": "X", "start_date": "2026-11-15", "end_date": "2026-11-13"})
        with pytest.raises(ValueError):
            rules.clean_map_fields({"name": "X", "start_date": "2026-11-13", "end_date": "2026-11-15",
                                    "daily_start": "20:00", "daily_end": "08:00"})
        with pytest.raises(ValueError):
            rules.clean_map_fields({"name": "X", "start_date": "2026-11-13", "end_date": "2026-11-15",
                                    "image_url": "https://evil.example/x.png"})


def _always_open(monkeypatch):
    real = rules.window_status
    monkeypatch.setattr(rules, "window_status",
                        lambda m, now=None: real(m, _utc(2026, 11, 13, 15, 0)))


@pytest.fixture()
def boston(admin_session):
    r = admin_session.post("/api/event-finder/admin/maps", json={
        "name": "Avatar of the Realm", "start_date": "2026-11-13", "end_date": "2026-11-15",
        "spots": [{"label": "Summit booth", "x": 20, "y": 30}, {"label": "Food court"}],
    })
    assert r.status_code == 200, r.get_json()
    return r.get_json()["map"]


class TestApi:
    def test_only_admins_manage_maps(self, user_session):
        r = user_session.post("/api/event-finder/admin/maps", json={
            "name": "X", "start_date": "2026-11-13", "end_date": "2026-11-15"})
        assert r.status_code == 403

    def test_share_and_view_by_link(self, client, boston, monkeypatch):
        _always_open(monkeypatch)
        with client.session_transaction() as sess:
            sess["user_id"] = "bruce_1"
            sess["username"] = "Bruce"
        me = client.get("/api/event-finder/me").get_json()
        token = me["share"]["token"]
        assert me["share"]["sharing"] is False
        assert me["share"]["url"].endswith(f"/find/{token}")

        # Nothing shown until sharing is on
        assert client.get(f"/api/event-finder/p/{token}").get_json()["live"] is False

        r = client.put("/api/event-finder/me", json={
            "map_id": boston["id"], "sharing": True, "x": 20, "y": 30, "label": "Summit booth"})
        assert r.status_code == 200
        with client.session_transaction() as sess:
            sess.clear()
        p = client.get(f"/api/event-finder/p/{token}").get_json()
        assert p["live"] is True and p["label"] == "Summit booth" and p["x"] == 20
        assert p["map"]["name"] == "Avatar of the Realm"
        assert client.get("/api/event-finder/p/not-a-token").status_code == 404

    def test_new_link_retires_old(self, user_session, boston):
        old = user_session.get("/api/event-finder/me").get_json()["share"]["token"]
        new = user_session.post("/api/event-finder/me/new-link").get_json()["share"]["token"]
        assert new != old
        assert user_session.get(f"/api/event-finder/p/{old}").status_code == 404

    def test_event_list_only_shows_listed_people(self, client, boston, monkeypatch):
        _always_open(monkeypatch)
        for uid, listed in (("a_1", True), ("b_1", False)):
            with client.session_transaction() as sess:
                sess["user_id"] = uid
                sess["username"] = uid.upper()
            client.put("/api/event-finder/me", json={
                "map_id": boston["id"], "sharing": True, "listed": listed, "label": "Table 4"})
        people = client.get(f"/api/event-finder/maps/{boston['id']}/people").get_json()["people"]
        assert [p["username"] for p in people] == ["A_1"]

    def test_event_list_empty_outside_hours(self, client, boston, monkeypatch):
        real = rules.window_status
        monkeypatch.setattr(rules, "window_status",
                            lambda m, now=None: real(m, _utc(2026, 11, 14, 3, 0)))
        with client.session_transaction() as sess:
            sess["user_id"] = "a_1"
        client.put("/api/event-finder/me", json={
            "map_id": boston["id"], "sharing": True, "listed": True, "label": "Table 4"})
        assert client.get(f"/api/event-finder/maps/{boston['id']}/people").get_json()["people"] == []

    def test_deleting_map_stops_sharing(self, admin_session, boston):
        admin_session.put("/api/event-finder/me", json={"map_id": boston["id"], "sharing": True})
        admin_session.delete(f"/api/event-finder/admin/maps/{boston['id']}")
        share = admin_session.get("/api/event-finder/me").get_json()["share"]
        assert share["sharing"] is False and share["map_id"] is None

    def test_qr_code(self, user_session):
        r = user_session.get("/api/event-finder/me/qr.png")
        assert r.status_code == 200 and r.mimetype == "image/png"
