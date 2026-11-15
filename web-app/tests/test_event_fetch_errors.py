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
