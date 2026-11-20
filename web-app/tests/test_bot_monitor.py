"""Tests for the admin Bot Traffic page: traffic rollups, classification and blocks."""

import pytest

import webapp_config
from services import bot_monitor
from utils import monitoring
from utils.site_gate import HEADER_NAME, issue_site_token

SCRAPER = "SorceryRec competitive archive/1.0"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "monitoring.db"
    monkeypatch.setattr(webapp_config, "MONITORING_DB_PATH", path)
    bot_monitor._seeded_dbs.clear()
    bot_monitor.clear_cache()
    monitoring.collector.flush()  # drop anything other tests left behind
    monitoring.init_db(path)
    yield path
    bot_monitor.clear_cache()


@pytest.fixture()
def gated(app, db):
    app.config["SITE_GATE_ENABLED"] = True
    yield app.test_client()


def _site(agent, ip="203.0.113.9"):
    return {"Sec-Fetch-Site": "same-origin", "User-Agent": agent, "CF-Connecting-IP": ip}


class TestClassify:
    @pytest.mark.parametrize("agent,kind", [
        ("Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)", "seo"),
        ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0)", "search"),
        ("Mozilla/5.0 (X11; Linux x86_64) Chrome/145.0.0.0 (compatible; meta-externalagent/1.1)", "ai"),
        ("Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)", "preview"),
        (SCRAPER, "bot"),
        ("curl/8.7.1", "script"),
        ("Mozilla/5.0 (Windows NT 10.0) HeadlessChrome/159.0 Safari/537.36", "script"),
        (CHROME, "browser"),
    ])
    def test_families(self, agent, kind):
        assert bot_monitor.classify_agent(agent) == kind


class TestBlockRules:
    def test_sorceryrec_is_seeded(self, db):
        assert bot_monitor.match_block(SCRAPER, "198.51.100.1")
        assert not bot_monitor.match_block(CHROME, "198.51.100.1")

    def test_refuses_rules_that_would_catch_browsers(self, db):
        for pattern in ("chrome", "Mozilla/5.0", "applewebkit/537", "safari/537.36"):
            with pytest.raises(bot_monitor.BlockError):
                bot_monitor.add_block("agent", pattern, "", "admin")
        with pytest.raises(bot_monitor.BlockError):
            bot_monitor.add_block("agent", "abc", "", "admin")  # too short
        with pytest.raises(bot_monitor.BlockError):
            bot_monitor.add_block("ip", "not an ip", "", "admin")

    def test_refuses_blocking_yourself(self, db):
        with pytest.raises(bot_monitor.BlockError):
            bot_monitor.add_block("agent", "mybrowser", "", "admin", own_agent="MyBrowser/1.0")
        with pytest.raises(bot_monitor.BlockError):
            bot_monitor.add_block("ip", "203.0.113.5", "", "admin", own_ip="203.0.113.5")

    def test_ip_block_and_removal(self, db):
        block = bot_monitor.add_block("ip", "203.0.113.7", "test", "admin")
        assert bot_monitor.match_block(CHROME, "203.0.113.7")
        bot_monitor.remove_block(block["id"], "admin")
        assert not bot_monitor.match_block(CHROME, "203.0.113.7")

    def test_removing_a_seeded_block_sticks(self, db):
        seeded = next(b for b in bot_monitor.list_blocks() if b["pattern"] == "sorceryrec")
        bot_monitor.remove_block(seeded["id"], "admin")
        bot_monitor._seeded_dbs.clear()  # e.g. a worker restart re-runs the seed
        bot_monitor.clear_cache()
        assert not bot_monitor.match_block(SCRAPER, "198.51.100.1")


class TestGate:
    def test_page_block_refuses_the_api(self, gated):
        assert gated.get("/api/site-token", headers=_site("Copycat/2.0")).status_code == 200
        bot_monitor.add_block("agent", "copycat", "", "admin")
        resp = gated.get("/api/site-token", headers=_site("Copycat/2.0"))
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "blocked_client"

    def test_ip_block_refuses_even_with_a_token(self, gated):
        bot_monitor.add_block("ip", "203.0.113.50", "", "admin")
        headers = {HEADER_NAME: issue_site_token(), **_site(CHROME, ip="203.0.113.50")}
        assert gated.get("/api/status", headers=headers).status_code == 403
        headers = {HEADER_NAME: issue_site_token(), **_site(CHROME, ip="203.0.113.51")}
        assert gated.get("/api/status", headers=headers).status_code == 200


class TestSummary:
    def _traffic(self, client, agent, ip, n, path="/api/status"):
        token = issue_site_token()
        for _ in range(n):
            client.get(path, headers={HEADER_NAME: token, **_site(agent, ip)})

    def test_rollup_flags_a_heavy_scraper_and_counts_blocks(self, gated, monkeypatch):
        monkeypatch.setattr(bot_monitor, "SUSPECT_DATA_PER_HOUR", 5)
        self._traffic(gated, CHROME, "203.0.113.1", 3)
        self._traffic(gated, CHROME, "203.0.113.1", 4, path="/api/me")  # polling noise
        self._traffic(gated, "Harvester/1.0", "203.0.113.2", 6)
        self._traffic(gated, SCRAPER, "203.0.113.3", 2)
        monitoring.collector.flush()

        summary = bot_monitor.bot_summary(24)
        by_agent = {c["user_agent"]: c for c in summary["clients"]}
        person = by_agent[CHROME]
        assert person["kind"] == "browser" and not person["suspect"]
        assert person["requests"] == 7 and person["data_requests"] == 3
        harvester = by_agent["Harvester/1.0"]
        assert harvester["kind"] == "script" and harvester["suspect"]
        assert harvester["peak_data_hour"] == 6 and harvester["ips"] == 1
        scraper = by_agent[SCRAPER]
        assert scraper["blocked"] == 2 and scraper["block_id"] is not None
        assert summary["totals"]["blocked"] == 2
        top_ip = summary["ips"][0]
        assert top_ip["ip"] == "203.0.113.2" and top_ip["top_agent"] == "Harvester/1.0"


class TestRoutes:
    @pytest.fixture()
    def admin(self, gated):
        with gated.session_transaction() as sess:
            sess["user_id"] = "admin_user_1"
            sess["username"] = "Admin"
        return gated

    def _h(self, agent=CHROME):
        return {HEADER_NAME: issue_site_token(), **_site(agent)}

    def test_needs_admin(self, gated):
        assert gated.get("/api/admin/bots", headers=self._h()).status_code in (401, 403)
        assert gated.post("/api/admin/bots/blocks", json={"kind": "agent", "pattern": "copycat"},
                          headers=self._h()).status_code in (401, 403)

    def test_block_and_unblock_round_trip(self, admin):
        resp = admin.post("/api/admin/bots/blocks", json={"kind": "agent", "pattern": "Copycat", "reason": "test"},
                          headers=self._h())
        assert resp.status_code == 200
        block = resp.get_json()["block"]
        assert block["pattern"] == "copycat" and block["active"] == 1
        data = admin.get("/api/admin/bots?hours=24", headers=self._h()).get_json()
        assert any(b["pattern"] == "copycat" and b["active"] for b in data["blocks"])
        assert admin.get("/api/site-token", headers=_site("Copycat/2")).status_code == 403
        assert admin.delete(f"/api/admin/bots/blocks/{block['id']}", headers=self._h()).status_code == 200
        assert admin.get("/api/site-token", headers=_site("Copycat/2")).status_code == 200
        assert admin.delete("/api/admin/bots/blocks/99999", headers=self._h()).status_code == 404

    def test_refuses_a_rule_that_blocks_browsers(self, admin):
        resp = admin.post("/api/admin/bots/blocks", json={"kind": "agent", "pattern": "Chrome"}, headers=self._h())
        assert resp.status_code == 400
