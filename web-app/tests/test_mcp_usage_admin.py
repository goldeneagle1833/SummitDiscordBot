"""Admin page "AI Apps (MCP)" section: GET /api/admin/mcp-usage reads the MCP server's usage log."""

from datetime import datetime, timezone

import pytest


@pytest.fixture
def usage_db(tmp_path, monkeypatch):
    from mcp_server import usage

    monkeypatch.setattr(usage, "DB_PATH", tmp_path / "mcp_usage.db")
    return usage


def test_admin_sees_ai_app_usage(admin_session, usage_db):
    usage = usage_db
    now = datetime.now(timezone.utc)
    usage.record("public", "meta_report", "ok", usage.caller_key(ip="1.2.3.4"), 200, now=now)
    usage.record("public", "meta_report", "error", usage.caller_key(ip="5.6.7.8"), 90000, now=now)
    usage.record("account", "my_match_review", "ok", usage.caller_key(player_id="42"), 800, now=now)
    usage.record("account", "my_decks", "ok", usage.caller_key(player_id="42"), 400, now=now)
    usage.record("public", usage.RATE_LIMITED_TOOL, "limited", usage.caller_key(ip="5.6.7.8"), now=now)

    r = admin_session.get("/api/admin/mcp-usage?days=7")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    t = body["totals"]
    assert t["calls"] == 5 and t["public"] == 3 and t["account"] == 2
    assert t["players"] == 1 and t["visitors"] == 2 and t["error"] == 1 and t["limited"] == 1
    tools = {x["tool"]: x for x in body["by_tool"]}
    assert tools["meta_report"]["calls"] == 2 and tools["meta_report"]["visitors"] == 2
    assert tools["my_match_review"]["players"] == 1 and tools["my_match_review"]["avg_ms"] == 800
    assert body["by_tool"][-1]["tool"] == usage.RATE_LIMITED_TOOL
    assert len(body["by_day"]) == 7 and body["by_day"][-1]["account"] == 2
    # No raw IPs or player ids in the answer
    text = r.get_data(as_text=True)
    assert "1.2.3.4" not in text and '"42"' not in text


def test_ai_app_usage_with_no_calls_yet(admin_session, usage_db):
    body = admin_session.get("/api/admin/mcp-usage?days=1").get_json()
    assert body["totals"]["calls"] == 0 and body["by_tool"] == [] and len(body["by_day"]) == 1


def test_ai_app_usage_is_admin_only(client, user_session, usage_db):
    assert client.get("/api/admin/mcp-usage").status_code in (401, 403)
    assert user_session.get("/api/admin/mcp-usage").status_code in (401, 403)
