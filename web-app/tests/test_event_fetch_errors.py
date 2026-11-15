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


def test_big_event_retries_in_compact_mode():
    calls = [_resp(400, COMPACT_400), _resp(200, _event_body([{"id": "r1"}]))]
    with patch("services.explorer.requests.get", side_effect=calls) as get:
        event = CuriosaService()._fetch_event_trpc("cmvrgzj9w004x08l0myf1wpen")
    assert event["players"] == [{"id": "r1"}]
    assert _sent_input(get.call_args_list[0]) == {"id": "cmvrgzj9w004x08l0myf1wpen"}
    assert _sent_input(get.call_args_list[1]) == {"id": "cmvrgzj9w004x08l0myf1wpen", "compact": True}


def test_small_event_sends_one_plain_request():
    with patch("services.explorer.requests.get", return_value=_resp(200, _event_body([]))) as get:
        ExplorerService()._fetch_event_trpc("abc")
    assert get.call_count == 1
    assert "compact" not in _sent_input(get.call_args)


def test_other_400_is_not_retried():
    with patch("services.explorer.requests.get", return_value=_resp(400, BAD_REQUEST)) as get:
        with pytest.raises(ValueError):
            CuriosaService()._fetch_event_trpc("abc")
    assert get.call_count == 1


def test_compact_payload_without_players_says_what_came_back():
    body = [{"result": {"data": {"json": {"event": {"title": "Big", "registrationCount": 300}}}}}]
    calls = [_resp(400, COMPACT_400), _resp(200, body)]
    with patch("services.explorer.requests.get", side_effect=calls):
        with pytest.raises(ValueError) as exc:
            CuriosaService()._fetch_event_trpc("abc")
    assert "without its player list" in str(exc.value)
    assert "registrationCount" in str(exc.value)
    assert "Internal error" not in _job_error_text(exc.value)
