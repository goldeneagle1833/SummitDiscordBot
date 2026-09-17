"""Tests for request/outbound/resource monitoring and the health endpoints."""

import time
from unittest.mock import patch

import pytest

import webapp_config
from repositories.monitoring import MonitoringRepository
from utils import monitoring
from utils.monitoring import (
    LATENCY_BUCKETS_MS,
    MetricsCollector,
    classify_service,
    histogram_index,
    percentile_from_histogram,
)


@pytest.fixture()
def metrics_db(tmp_path, monkeypatch):
    db = tmp_path / "monitoring.db"
    monkeypatch.setattr(webapp_config, "MONITORING_DB_PATH", db)
    monkeypatch.setattr("services.monitoring._health_cache", None)
    monitoring.init_db()
    return db


class TestHistogram:
    def test_histogram_index_boundaries(self):
        assert histogram_index(0) == 0
        assert histogram_index(50) == 0
        assert histogram_index(51) == 1
        assert histogram_index(999_999) == len(LATENCY_BUCKETS_MS)

    def test_percentile_empty(self):
        assert percentile_from_histogram([0] * 10, 0.95) is None

    def test_percentile_interpolates_within_bucket(self):
        # 90 fast (0-50ms), 10 slow (500-1000ms)
        counts = [90, 0, 0, 0, 10, 0, 0, 0, 0, 0]
        assert percentile_from_histogram(counts, 0.50) == 28   # 50/90 of the way to 50ms
        assert percentile_from_histogram(counts, 0.95) == 750  # halfway through 500-1000ms
        assert percentile_from_histogram(counts, 1.0) == 1000

    def test_percentile_overflow_is_none(self):
        counts = [0] * 9 + [5]
        assert percentile_from_histogram(counts, 0.95) is None


class TestClassifyService:
    @pytest.mark.parametrize("url,expected", [
        ("https://curiosa.io/api/decks/1", "curiosa"),
        ("https://api.curiosa.io/trpc/event.get", "curiosa"),
        ("https://discord.com/api/users/@me", "discord"),
        ("https://www.googleapis.com/oauth2/v2/userinfo", "google"),
        ("http://127.0.0.1:8765/users/0/status", "bot_api"),
        ("https://example.org/x", "example.org"),
    ])
    def test_classify(self, url, expected):
        assert classify_service(url) == expected


class TestCollectorFlush:
    def test_workers_merge_into_same_bucket(self, metrics_db):
        # Two collectors simulate two gunicorn workers writing the same minute
        a, b = MetricsCollector(), MetricsCollector()
        a.record_request("GET", "/api/leaderboard", 200, 40)
        a.record_request("GET", "/api/leaderboard", 500, 1200)
        b.record_request("GET", "/api/leaderboard", 404, 80)
        a.flush()
        b.flush()

        [row] = MonitoringRepository().endpoint_summary(hours=1)
        assert row["count"] == 3
        assert row["errors_4xx"] == 1
        assert row["errors_5xx"] == 1
        assert row["max_ms"] == 1200
        assert sum(row["histogram"]) == 3

    def test_external_errors_include_connection_failures(self, metrics_db):
        c = MetricsCollector()
        c.record_external("curiosa", 200, 300)
        c.record_external("curiosa", None, 15000)  # timeout / connection error
        c.flush()

        [row] = MonitoringRepository().external_summary(hours=1)
        assert row["service"] == "curiosa"
        assert row["count"] == 2
        assert row["errors"] == 1
        assert row["error_rate"] == 50.0

    def test_flush_is_noop_when_empty(self, metrics_db):
        MetricsCollector().flush()
        assert MonitoringRepository().request_totals(hours=1)["count"] == 0

    def test_resource_sample_roundtrip(self, metrics_db):
        sample = monitoring.sample_resources()
        assert 0 <= sample["disk_percent"] <= 100
        monitoring.write_resource_sample(sample)

        latest = MonitoringRepository().latest_resources()
        assert latest is not None
        assert latest["workers"][0]["pid"] == sample["pid"]
        assert MonitoringRepository().resource_timeseries(hours=1)

    def test_prune_removes_old_rows(self, metrics_db):
        c = MetricsCollector()
        with patch.object(MetricsCollector, "_bucket", return_value=int(time.time()) - 30 * 86400):
            c.record_request("GET", "/old", 200, 10)
        c.record_request("GET", "/new", 200, 10)
        c.flush()
        monitoring.prune(days=7)

        endpoints = [r["endpoint"] for r in MonitoringRepository().endpoint_summary(hours=24 * 60)]
        assert endpoints == ["/new"]


class TestRequestInstrumentation:
    def test_request_is_recorded_by_url_rule(self, client, metrics_db):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        assert resp.headers["Server-Timing"].startswith("app;dur=")

        monitoring.collector.flush()
        endpoints = {r["endpoint"] for r in MonitoringRepository().endpoint_summary(hours=1)}
        assert "/api/status" in endpoints

    def test_cf_ray_used_as_request_id(self, client, metrics_db):
        resp = client.get("/api/status", headers={"CF-Ray": "abc123-DFW"})
        assert resp.headers["X-Request-ID"] == "abc123-DFW"

    def test_unhandled_exception_recorded(self, app, metrics_db):
        @app.route("/boom-test")
        def boom():
            raise RuntimeError("kaboom")

        app.config["PROPAGATE_EXCEPTIONS"] = False
        resp = app.test_client().get("/boom-test")
        assert resp.status_code == 500

        monitoring.collector.flush()
        errors = MonitoringRepository().recent_errors(hours=1)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "RuntimeError"
        assert errors[0]["message"] == "kaboom"


class TestHealthEndpoint:
    def test_health_ok_hides_details(self, client, metrics_db):
        with patch("services.monitoring._check_bot_api", return_value=(True, "ok", 1.0)):
            resp = client.get("/api/health")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] in ("ok", "degraded")
        assert isinstance(data["failing"], list)
        assert "checks" not in data

    def test_health_down_when_critical_db_missing(self, client, metrics_db, tmp_path, monkeypatch):
        monkeypatch.setattr(webapp_config, "ELO_DB_PATH", tmp_path / "nope.db")
        with patch("services.monitoring._check_bot_api", return_value=(True, "ok", 1.0)):
            from services.monitoring import get_health
            result = get_health(use_cache=False)
            resp = client.get("/api/health")
        assert result["status"] == "down"
        assert result["checks"]["db:elo"]["detail"] == "missing"
        assert resp.status_code == 503
        assert "db:elo" in resp.get_json()["failing"]

    def test_bot_api_down_is_degraded_not_down(self, metrics_db):
        from services.monitoring import get_health
        with patch("services.monitoring._check_bot_api", return_value=(False, "ConnectionError", None)):
            result = get_health(use_cache=False)
        assert result["checks"]["bot_api"]["ok"] is False
        assert result["status"] != "ok"


class TestMonitoringDashboard:
    def test_requires_admin(self, user_session, metrics_db):
        assert user_session.get("/api/admin/monitoring").status_code == 403

    def test_admin_gets_dashboard(self, admin_session, metrics_db):
        with patch("services.monitoring._check_bot_api", return_value=(True, "ok", 1.0)):
            resp = admin_session.get("/api/admin/monitoring?hours=6")
        assert resp.status_code == 200
        data = resp.get_json()
        for key in ("health", "totals", "endpoints", "external", "traffic",
                    "resources", "errors", "databases"):
            assert key in data
        assert data["hours"] == 6

    def test_rejects_bad_hours(self, admin_session, metrics_db):
        assert admin_session.get("/api/admin/monitoring?hours=abc").status_code == 400
