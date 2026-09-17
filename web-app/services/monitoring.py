"""Health checks and the admin monitoring dashboard payload."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path

import requests

import webapp_config
from repositories.monitoring import MonitoringRepository
from utils.monitoring import SLOW_REQUEST_MS
from utils.version import APP_VERSION

logger = logging.getLogger(__name__)

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

# Degraded thresholds
DISK_WARN_PERCENT = 90
MEMORY_WARN_PERCENT = 90
ERROR_RATE_WARN_PERCENT = 5
ERROR_RATE_MIN_REQUESTS = 20   # don't flag a 1-of-3 blip
RECENT_WINDOW_HOURS = 10 / 60
BOT_API_TIMEOUT_S = 2
HEALTH_CACHE_TTL_S = 15        # /api/health is public; don't let it be a load amplifier

_PROCESS_STARTED = time.time()
_health_cache: tuple[float, dict] | None = None
_health_lock = threading.Lock()


def _databases() -> dict[str, tuple[Path, bool]]:
    """name -> (path, critical). Critical DB failures mark the app down."""
    from repositories.store import STORE_DB_PATH
    return {
        "elo": (webapp_config.ELO_DB_PATH, True),
        "match_records": (webapp_config.MATCH_RECORDS_DB_PATH, True),
        "community": (webapp_config.COMMUNITY_DB_PATH, False),
        "fart_scores": (webapp_config.FART_SCORES_DB_PATH, False),
        "analytics": (webapp_config.ANALYTICS_DB_PATH, False),
        "explorer": (webapp_config.EXPLORER_DB_PATH, False),
        "rumble": (webapp_config.RUMBLE_DB_PATH, False),
        "deck_builder": (webapp_config.DECK_BUILDER_DB_PATH, False),
        "feedback": (webapp_config.FEEDBACK_DB_PATH, False),
        "store": (STORE_DB_PATH, False),
        "monitoring": (webapp_config.MONITORING_DB_PATH, False),
    }


def _check_database(path: Path) -> tuple[bool, str, float | None]:
    if not path.exists():
        return False, "missing", None
    start = time.perf_counter()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return False, type(e).__name__, None
    return True, "ok", round((time.perf_counter() - start) * 1000, 1)


def _check_bot_api() -> tuple[bool, str, float | None]:
    base_url = os.getenv("MATCHMAKING_BOT_API_URL", "http://127.0.0.1:8765").rstrip("/")
    start = time.perf_counter()
    try:
        resp = requests.get(
            f"{base_url}/users/0/status",
            headers={"X-API-Key": webapp_config.DRAFT_SORCERY_API_KEY},
            timeout=BOT_API_TIMEOUT_S,
        )
    except requests.RequestException as e:
        return False, type(e).__name__, None
    ms = round((time.perf_counter() - start) * 1000, 1)
    if resp.status_code >= 500:
        return False, f"HTTP {resp.status_code}", ms
    return True, "ok", ms


def _compute_health() -> dict:
    checks: dict[str, dict] = {}
    status = "ok"

    def flag(level: str):
        nonlocal status
        if level == "down" or (level == "degraded" and status == "ok"):
            status = level

    for name, (path, critical) in _databases().items():
        ok, detail, ms = _check_database(path)
        checks[f"db:{name}"] = {"ok": ok, "detail": detail, "ms": ms}
        if not ok:
            flag("down" if critical else "degraded")

    disk = shutil.disk_usage(str(webapp_config.BASE_DIR))
    disk_percent = round(disk.used / disk.total * 100, 1)
    checks["disk"] = {"ok": disk_percent < DISK_WARN_PERCENT, "detail": f"{disk_percent}% used"}
    if disk_percent >= DISK_WARN_PERCENT:
        flag("degraded")

    if psutil is not None:
        mem_percent = psutil.virtual_memory().percent
        checks["memory"] = {"ok": mem_percent < MEMORY_WARN_PERCENT, "detail": f"{mem_percent}% used"}
        if mem_percent >= MEMORY_WARN_PERCENT:
            flag("degraded")

    ok, detail, ms = _check_bot_api()
    checks["bot_api"] = {"ok": ok, "detail": detail, "ms": ms}
    if not ok:
        flag("degraded")

    try:
        recent = MonitoringRepository().request_totals(RECENT_WINDOW_HOURS)
        noisy = (recent["count"] >= ERROR_RATE_MIN_REQUESTS
                 and recent["error_rate_5xx"] >= ERROR_RATE_WARN_PERCENT)
        checks["api_errors"] = {
            "ok": not noisy,
            "detail": f"{recent['error_rate_5xx']}% 5xx over {recent['count']} requests (10m)",
        }
        p95 = recent["p95_ms"]  # None with count > 0 means beyond the largest histogram bucket
        p95_slow = p95 is None or p95 > SLOW_REQUEST_MS * 2.5
        slow = recent["count"] >= ERROR_RATE_MIN_REQUESTS and p95_slow
        p95_label = f"~{p95}ms" if p95 is not None else ("n/a" if not recent["count"] else "> 30s")
        checks["api_latency"] = {"ok": not slow, "detail": f"p95 {p95_label} (10m)"}
        if noisy or slow:
            flag("degraded")
    except sqlite3.Error as e:
        checks["api_errors"] = {"ok": False, "detail": f"metrics unavailable: {type(e).__name__}"}
        flag("degraded")

    return {
        "status": status,
        "version": APP_VERSION,
        "uptime_s": int(time.time() - _PROCESS_STARTED),
        "checked_at": int(time.time()),
        "checks": checks,
    }


def get_health(use_cache: bool = True) -> dict:
    global _health_cache
    now = time.time()
    if use_cache and _health_cache and now - _health_cache[0] < HEALTH_CACHE_TTL_S:
        return _health_cache[1]
    with _health_lock:
        if use_cache and _health_cache and now - _health_cache[0] < HEALTH_CACHE_TTL_S:
            return _health_cache[1]
        result = _compute_health()
        _health_cache = (time.time(), result)
        return result


def _database_sizes() -> list[dict]:
    sizes = []
    for name, (path, _critical) in _databases().items():
        size = 0
        # WAL/SHM sidecars can grow large and are easy to miss
        for suffix in ("", "-wal", "-shm"):
            p = Path(f"{path}{suffix}")
            if p.exists():
                size += p.stat().st_size
        sizes.append({"name": name, "size_mb": round(size / 1024 ** 2, 2), "exists": path.exists()})
    return sorted(sizes, key=lambda d: d["size_mb"], reverse=True)


def get_dashboard(hours: float) -> dict:
    repo = MonitoringRepository()
    return {
        "hours": hours,
        "health": get_health(use_cache=False),
        "totals": repo.request_totals(hours),
        "endpoints": repo.endpoint_summary(hours),
        "external": repo.external_summary(hours),
        "traffic": repo.traffic_timeseries(hours),
        "resources": repo.resource_timeseries(hours),
        "resources_now": repo.latest_resources(),
        "errors": repo.recent_errors(hours),
        "databases": _database_sizes(),
        "slow_request_ms": SLOW_REQUEST_MS,
    }
