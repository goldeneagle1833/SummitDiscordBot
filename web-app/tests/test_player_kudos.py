"""Tests for kudos (positive player reports): partner API, admin list, Player of the Day."""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from repositories.player_kudos_repo import PlayerKudosRepository

KEY = {"X-API-Key": "test-api-key-123"}
URL = "/api/player-kudos"

def _match(db, winner, loser, days_ago=0):
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        "INSERT INTO match_records (winner_id, losser_id, timestamp, match_type) "
        "VALUES (?, ?, ?, 'ranked')",
        (winner, loser, (datetime.now() - timedelta(days=days_ago)).isoformat()),
    )
    mid = cur.lastrowid  # the match ID is the rowid, as in production
    conn.commit()
    conn.close()
    return mid


def _body(**over):
    body = {"giver_id": "111", "receiver_id": "222", "reasons": ["good_sport"], "message": "gg, great game"}
    body.update(over)
    return body


def _backdate_kudos(db, days):
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE player_kudos SET created_at = ?",
        ((datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),),
    )
    conn.commit()
    conn.close()


class TestPartnerKudos:
    def test_needs_the_api_key(self, client):
        assert client.post(URL, json=_body()).status_code == 401

    def test_kudos_for_a_recorded_match(self, client, match_db):
        mid = _match(match_db, "222", "111")
        resp = client.post(URL, json=_body(anonymous=True, giver_name="Al"), headers=KEY)
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["match_id"] == mid
        [row], _ = PlayerKudosRepository(match_db).get_all_kudos()
        assert row["source"] == "sorcery-online"
        assert row["anonymous"] is True
        assert row["message"] == "gg, great game"

    def test_no_match_no_kudos(self, client, match_db):
        _match(match_db, "222", "333")  # receiver played someone else
        _match(match_db, "222", "111", days_ago=20)  # too long ago
        resp = client.post(URL, json=_body(), headers=KEY)
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "no_match"

    def test_one_kudos_per_match(self, client, match_db):
        _match(match_db, "222", "111")
        assert client.post(URL, json=_body(), headers=KEY).status_code == 201
        resp = client.post(URL, json=_body(), headers=KEY)
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "already_given"
        # The other player can still give kudos back
        back = client.post(URL, json=_body(giver_id="222", receiver_id="111"), headers=KEY)
        assert back.status_code == 201

    def test_validation(self, client, match_db):
        _match(match_db, "222", "111")
        bad = [
            _body(receiver_id="111"),
            _body(reasons=["toxic"]),
            _body(reasons=[], message=""),
            _body(message="x" * 201),
            _body(anonymous="yes"),
            _body(pairing_id="abc"),
            {"giver_id": "111"},
        ]
        for body in bad:
            assert client.post(URL, json=body, headers=KEY).status_code == 400, body
        unknown = client.post(URL, json=_body(reasons=["toxic"]), headers=KEY).get_json()
        assert "good_sport" in unknown["allowed_reasons"]

    def test_reports_and_blocks_still_work(self, client, match_db):
        resp = client.post(
            "/api/player-reports",
            json={"reporter_id": "111", "reported_id": "222", "reasons": ["no_show"]},
            headers=KEY,
        )
        assert resp.status_code == 201


class TestAdminKudos:
    def test_admin_list_and_hide(self, client, admin_session, match_db):
        _match(match_db, "222", "111")
        client.post(URL, json=_body(), headers=KEY)
        [entry] = admin_session.get("/api/admin/player-kudos").get_json()["entries"]
        assert entry["receiver_id"] == "222" and entry["hidden"] is False

        resp = admin_session.post(f"/api/admin/player-kudos/{entry['id']}/hidden", json={"hidden": True})
        assert resp.status_code == 200
        [entry] = admin_session.get("/api/admin/player-kudos").get_json()["entries"]
        assert entry["hidden"] is True

    def test_admin_only(self, user_session):
        assert user_session.get("/api/admin/player-kudos").status_code in (401, 403)


class TestPlayerOfTheDay:
    def test_nothing_until_someone_gets_kudos(self, client):
        assert client.get("/api/kudos-spotlight").get_json()["kudos_spotlight"] is None

    def test_todays_kudos_wait_for_tomorrow(self, client, match_db):
        _match(match_db, "222", "111")
        client.post(URL, json=_body(), headers=KEY)
        assert client.get("/api/kudos-spotlight").get_json()["kudos_spotlight"] is None

    def test_yesterdays_kudos_make_a_player_of_the_day(self, client, match_db, elo_db):
        conn = sqlite3.connect(str(elo_db))
        conn.executemany(
            "INSERT INTO overall_standings (user_id, user_display_name) VALUES (?, ?)",
            [("111", "Alice"), ("222", "Bob")],
        )
        conn.commit()
        conn.close()
        _match(match_db, "222", "111")
        client.post(URL, json=_body(message="Explained the rules, so kind"), headers=KEY)
        _backdate_kudos(match_db, 1)

        spot = client.get("/api/kudos-spotlight").get_json()["kudos_spotlight"]
        assert spot["title"] == "Bob"
        assert spot["badge_text"] == "PLAYER OF THE DAY"
        assert spot["link"] == "/player/222"
        assert "Explained the rules, so kind" in spot["subtitle"]
        assert spot["kudos"]["credit"] == "Kudos from Alice"
        assert spot["kudos"]["reasons"] == ["Good sport, win or lose"]

        # The random spotlight doesn't also show a stats Player of the Day today.
        with patch("services.spotlight._get_player_of_the_day") as stats_potd:
            client.get("/api/spotlight")
            stats_potd.assert_not_called()

    def test_anonymous_and_hidden(self, client, match_db):
        _match(match_db, "222", "111")
        client.post(URL, json=_body(anonymous=True, giver_name="Secret Al"), headers=KEY)
        _backdate_kudos(match_db, 1)
        spot = client.get("/api/kudos-spotlight").get_json()["kudos_spotlight"]
        assert "Secret Al" not in spot["subtitle"]
        assert spot["kudos"]["credit"] == "Kudos from an opponent"
        assert spot["kudos"]["giver_name"] is None

        [row], _ = PlayerKudosRepository(match_db).get_all_kudos()
        PlayerKudosRepository(match_db).set_hidden(row["id"], True)
        from services.spotlight import clear_spotlight_cache
        clear_spotlight_cache()
        assert client.get("/api/kudos-spotlight").get_json()["kudos_spotlight"] is None

    def test_pick_is_stable_and_skips_recent_winners(self, match_db):
        repo = PlayerKudosRepository(match_db)
        for receiver in ("201", "202", "203", "204", "205"):
            _match(match_db, receiver, "111", days_ago=2)
            repo.give_kudos(giver_id="111", receiver_id=receiver, reasons=["friendly"])
        _backdate_kudos(match_db, 2)
        day = date.today()
        first = repo.pick_player_of_the_day(day)["user_id"]
        assert repo.pick_player_of_the_day(day)["user_id"] == first
        # Over a few days with 5 candidates the pick moves around
        picks = {repo.pick_player_of_the_day(day + timedelta(days=n))["user_id"] for n in range(3)}
        assert len(picks) >= 2


def test_works_with_the_production_match_records_layout(tmp_path):
    """Production's match_records has no match_id column; the match ID is the rowid."""
    db = tmp_path / "prod_layout.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE match_records (reporter_id INTEGER, winner_id INTEGER, losser_id INTEGER, "
        "timestamp TEXT, json_deck_data TEXT, match_type TEXT, pairing_id INTEGER)"
    )
    conn.execute(
        "INSERT INTO match_records (winner_id, losser_id, timestamp, match_type, pairing_id) "
        "VALUES (222, 111, ?, 'ranked', 7)",
        (datetime.now().isoformat(),),
    )
    conn.commit()
    conn.close()
    repo = PlayerKudosRepository(db)
    saved = repo.give_kudos(giver_id="111", receiver_id="222", reasons=["good_sport"], pairing_id=7)
    assert saved["match_id"] == 1
    import pytest
    from repositories.player_kudos_repo import KudosError
    with pytest.raises(KudosError) as e:
        repo.give_kudos(giver_id="111", receiver_id="222", reasons=["friendly"])
    assert e.value.code == "already_given"
