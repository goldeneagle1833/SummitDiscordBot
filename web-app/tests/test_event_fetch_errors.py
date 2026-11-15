"""sorcerytcg.com event lookup failures show the site's own reason."""
from unittest.mock import MagicMock, patch

import pytest

from routes.api.events import _job_error_text
from services.curiosa import CuriosaService
from services.explorer import (
    ExplorerFetchError,
    ExplorerService,
    event_fetch_error_message,
    trpc_error_detail,
)


def _resp(status, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    if body is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = body
    resp.text = text
    return resp


BAD_REQUEST = [{
    "error": {"json": {
        "message": '[{"code":"invalid_type","path":["eventId"],"message":"Required"}]',
        "code": -32600,
        "data": {"code": "BAD_REQUEST", "httpStatus": 400},
    }}
}]


def test_detail_reads_zod_issues():
    assert trpc_error_detail(_resp(400, BAD_REQUEST)) == "BAD_REQUEST: eventId: Required"


def test_detail_plain_message():
    body = [{"error": {"json": {"message": "Event too large", "data": {"code": "BAD_REQUEST"}}}}]
    assert trpc_error_detail(_resp(400, body)) == "BAD_REQUEST: Event too large"


def test_detail_non_json_body():
    assert trpc_error_detail(_resp(400, text="  Bad Request  ")) == "Bad Request"


def test_messages_by_status():
    assert "couldn't find event abc" in event_fetch_error_message(404, "abc", "")
    assert "private" in event_fetch_error_message(403, "abc", "")
    assert "Try again" in event_fetch_error_message(502, "abc", "")
    msg = event_fetch_error_message(400, "abc", "BAD_REQUEST: x")
    assert "refused our request" in msg and msg.endswith("Their reply: BAD_REQUEST: x")


def test_importer_error_includes_reason():
    with patch("services.curiosa.requests.get", return_value=_resp(400, BAD_REQUEST)):
        with pytest.raises(ValueError) as exc:
            CuriosaService()._fetch_event_trpc("cmvrgzj9w004x08l0myf1wpen")
    assert "eventId: Required" in str(exc.value)
    assert "Internal error" not in _job_error_text(exc.value)


def test_explorer_error_includes_reason():
    with patch("services.explorer.requests.get", return_value=_resp(400, BAD_REQUEST)):
        with pytest.raises(ExplorerFetchError) as exc:
            ExplorerService()._fetch_event_trpc("abc")
    assert "eventId: Required" in str(exc.value)


def test_unexpected_errors_keep_internal_label():
    assert _job_error_text(KeyError("x")).startswith("Internal error")


COMPACT_400 = [{
    "error": {"json": {
        "message": '[{"code":"invalid_value","path":["compact"],"message":"Invalid input: expected true"}]',
        "data": {"code": "BAD_REQUEST", "httpStatus": 400},
    }}
}]


def _event_body(players):
    return [{"result": {"data": {"json": {"event": {"title": "Big", "players": players}}}}}]


def _sent_input(call):
    import json
    return json.loads(call.kwargs["params"]["input"])["0"]["json"]


def test_event_get_always_sends_compact():
    with patch("services.explorer.requests.get", return_value=_resp(200, _event_body([{"id": "r1"}]))) as get:
        event = CuriosaService()._fetch_event_trpc("cmvrgzj9w004x08l0myf1wpen")
    assert event["players"] == [{"id": "r1"}]
    assert get.call_count == 1
    assert _sent_input(get.call_args) == {"id": "cmvrgzj9w004x08l0myf1wpen", "compact": True}


def test_compact_payload_without_players_says_what_came_back():
    body = [{"result": {"data": {"json": {"event": {"title": "Big", "registrationCount": 300}}}}}]
    with patch("services.explorer.requests.get", return_value=_resp(200, body)):
        with pytest.raises(ValueError) as exc:
            CuriosaService()._fetch_event_trpc("abc")
    assert "without its player list" in str(exc.value)
    assert "registrationCount" in str(exc.value)
    assert "Internal error" not in _job_error_text(exc.value)


def _seat(reg, name, result, score):
    return {
        "registrationId": reg,
        "result": {"isBye": False, "score": score, "result": result},
        "registration": {"id": reg, "user": {"id": "u-" + reg, "displayname": name}},
    }


def _compact_event():
    """Shape copied from the live compact reply (Avatar of the Realm 2026)."""
    return {
        "title": "Avatar of the Realm 2026 Championship",
        "startsAt": "2026-11-14T14:00:00.000Z",
        "topcut": {"size": 8},
        "players": [
            {"id": "a", "status": "Ready", "user": {"displayname": "Ann", "username": "ann"}},
            {"id": "b", "status": "Ready", "user": {"displayname": "Bob", "username": "bob"}},
        ],
        "phases": [
            {"number": 2, "structure": "SingleElimination", "type": "Play", "roundCount": 3, "rounds": [
                {"number": 1, "pairings": [{"seats": [_seat("a", "Ann", "Win", 3), _seat("b", "Bob", "Loss", 0)]}]},
            ]},
            {"number": 1, "structure": "Swiss", "type": "Play", "roundCount": 9, "rounds": [
                {"number": 1, "pairings": [{"seats": [_seat("a", "Ann", "Loss", 0), _seat("b", "Bob", "Win", 3)]}]},
                {"number": 2, "pairings": [{"seats": [_seat("a", "Ann", "Win", 3), _seat("b", "Bob", "Loss", 0)]}]},
            ]},
        ],
    }


def test_compact_reply_rebuilds_match_history():
    body = [{"result": {"data": {"json": {"event": _compact_event()}}}}]
    with patch("services.explorer.requests.get", return_value=_resp(200, body)), \
            patch.object(CuriosaService, "_fetch_page_html", return_value=""):
        result = CuriosaService().fetch_event_deck_ids(
            "https://sorcerytcg.com/events/cmvrgzj9w004x08l0myf1wpen", with_decks=False
        )
    history = {p["display_name"]: p for p in result["match_history"]}
    assert set(history) == {"Ann", "Bob"}
    ann = history["Ann"]
    assert (ann["wins"], ann["losses"]) == (2, 1)
    # Top cut runs on after the 9 Swiss rounds and sorts first.
    assert [m["round"] for m in ann["matches"]] == [10, 2, 1]
    assert ann["matches"][0]["phase"] == "SingleElimination"
    assert ann["matches"][0]["opponent"]["display_name"] == "Bob"
    assert ann["matches"][-1]["result"] == "Loss"


def test_full_reply_seats_are_left_alone():
    from services.explorer import attach_seats_from_phases
    event = _compact_event()
    event["players"][0]["seats"] = [{"round": {"number": 1}}]
    attach_seats_from_phases(event)
    assert event["players"][0]["seats"] == [{"round": {"number": 1}}]
    assert "seats" not in event["players"][1]


def test_round_numbers_already_running_on_are_kept():
    """Live data numbers top-cut rounds 10-12 after 9 Swiss rounds."""
    from services.explorer import attach_seats_from_phases
    event = _compact_event()
    event["phases"][0]["rounds"][0]["number"] = 10
    attach_seats_from_phases(event)
    assert sorted(s["round"]["number"] for s in event["players"][0]["seats"]) == [1, 2, 10]
