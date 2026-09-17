"""In-process API and resource monitoring.

Three things are measured, all written to ``MONITORING_DB_PATH``:

- **Inbound requests**: timed in ``before_request``/``after_request`` and
  grouped by Flask URL rule (``/api/player/<user_id>``, not the raw path) so
  cardinality stays small.
- **Outbound HTTP calls**: every ``requests`` call (Curiosa, Discord OAuth,
  YouTube, the bot loopback API, ...) is timed by wrapping
  ``requests.Session.request`` and grouped by service.
- **Resources**: a daemon thread samples process RSS/CPU/threads/FDs plus
  system memory, CPU, load and disk every ``SAMPLE_INTERVAL_S``.

Each gunicorn worker aggregates in memory and flushes per-minute rollups with
an UPSERT, so rows from multiple workers merge into the same bucket.
Latency is stored as a fixed histogram so percentiles can be approximated
after aggregation.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from flask import Flask, g, got_request_exception, request

import webapp_config

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is in requirements.txt
    psutil = None

logger = logging.getLogger(__name__)

# Upper bounds (ms) of latency histogram buckets; a final overflow bucket follows.
LATENCY_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)
HISTOGRAM_COLUMNS = [f"le_{b}" for b in LATENCY_BUCKETS_MS] + ["le_inf"]

SLOW_REQUEST_MS = 1000
FLUSH_INTERVAL_S = 30
SAMPLE_INTERVAL_S = 60
RETENTION_DAYS = 7
MAX_ERROR_MESSAGE_LEN = 500

# Hostname suffix -> service label for outbound calls
EXTERNAL_SERVICES = {
    "curiosa.io": "curiosa",
    "discord.com": "discord",
    "discordapp.com": "discord",
    "googleapis.com": "google",
    "google.com": "google",
    "youtube.com": "youtube",
    "stripe.com": "stripe",
    "openai.com": "openai",
    "127.0.0.1": "bot_api",
    "localhost": "bot_api",
}

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS request_metrics (
    bucket INTEGER NOT NULL,
    method TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    errors_4xx INTEGER NOT NULL DEFAULT 0,
    errors_5xx INTEGER NOT NULL DEFAULT 0,
    total_ms REAL NOT NULL DEFAULT 0,
    max_ms REAL NOT NULL DEFAULT 0,
    {", ".join(f"{c} INTEGER NOT NULL DEFAULT 0" for c in HISTOGRAM_COLUMNS)},
    PRIMARY KEY (bucket, method, endpoint)
);
CREATE TABLE IF NOT EXISTS external_metrics (
    bucket INTEGER NOT NULL,
    service TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    total_ms REAL NOT NULL DEFAULT 0,
    max_ms REAL NOT NULL DEFAULT 0,
    {", ".join(f"{c} INTEGER NOT NULL DEFAULT 0" for c in HISTOGRAM_COLUMNS)},
    PRIMARY KEY (bucket, service)
);
CREATE TABLE IF NOT EXISTS resource_samples (
    ts INTEGER NOT NULL,
    pid INTEGER NOT NULL,
    rss_mb REAL,
    cpu_percent REAL,
    threads INTEGER,
    open_fds INTEGER,
    sys_cpu_percent REAL,
    sys_mem_percent REAL,
    sys_mem_available_mb REAL,
    load_1m REAL,
    disk_percent REAL,
    disk_free_gb REAL
);
CREATE INDEX IF NOT EXISTS idx_resource_samples_ts ON resource_samples(ts);
CREATE TABLE IF NOT EXISTS error_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    request_id TEXT,
    method TEXT,
    endpoint TEXT,
    path TEXT,
    status INTEGER,
    error_type TEXT,
    message TEXT
);
CREATE INDEX IF NOT EXISTS idx_error_events_ts ON error_events(ts);
"""


def connect(db_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or webapp_config.MONITORING_DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None) -> None:
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def histogram_index(ms: float) -> int:
    for i, bound in enumerate(LATENCY_BUCKETS_MS):
        if ms <= bound:
            return i
    return len(LATENCY_BUCKETS_MS)


def percentile_from_histogram(counts: list[int], pct: float) -> int | None:
    """Estimate a percentile by linear interpolation inside its histogram bucket
    (the same approach as Prometheus' ``histogram_quantile``).

    Returns None when there are no samples or the percentile falls in the
    overflow bucket (slower than the largest bound) - callers with a non-zero
    count should render that as "> LATENCY_BUCKETS_MS[-1]".
    """
    total = sum(counts)
    if not total:
        return None
    target = total * pct
    running = 0
    for i, c in enumerate(counts):
        if c and running + c >= target:
            if i >= len(LATENCY_BUCKETS_MS):
                return None
            lower = LATENCY_BUCKETS_MS[i - 1] if i else 0
            upper = LATENCY_BUCKETS_MS[i]
            return round(lower + (upper - lower) * (target - running) / c)
        running += c
    return None


def classify_service(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for suffix, name in EXTERNAL_SERVICES.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return host or "unknown"


@dataclass
class _Stats:
    count: int = 0
    errors_4xx: int = 0
    errors_5xx: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    histogram: list[int] = field(default_factory=lambda: [0] * len(HISTOGRAM_COLUMNS))

    def add(self, ms: float, status: int | None) -> None:
        self.count += 1
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)
        self.histogram[histogram_index(ms)] += 1
        if status is None or status >= 500:
            self.errors_5xx += 1
        elif status >= 400:
            self.errors_4xx += 1


class MetricsCollector:
    """Per-process aggregator; thread-safe; flushes rollups to SQLite."""

    def __init__(self):
        self._lock = threading.Lock()
        self._requests: dict[tuple[int, str, str], _Stats] = {}
        self._external: dict[tuple[int, str], _Stats] = {}
        self._errors: list[tuple] = []

    @staticmethod
    def _bucket(now: float | None = None) -> int:
        now = time.time() if now is None else now
        return int(now // 60 * 60)

    def record_request(self, method: str, endpoint: str, status: int, ms: float) -> None:
        key = (self._bucket(), method, endpoint)
        with self._lock:
            self._requests.setdefault(key, _Stats()).add(ms, status)

    def record_external(self, service: str, status: int | None, ms: float) -> None:
        key = (self._bucket(), service)
        with self._lock:
            self._external.setdefault(key, _Stats()).add(ms, status)

    def record_error(self, *, request_id, method, endpoint, path, status, error_type, message) -> None:
        row = (int(time.time()), request_id, method, endpoint, path, status,
               error_type, (message or "")[:MAX_ERROR_MESSAGE_LEN])
        with self._lock:
            # Bound memory if the DB is unwritable during an error storm
            if len(self._errors) < 1000:
                self._errors.append(row)

    def flush(self, db_path=None) -> None:
        with self._lock:
            requests_, self._requests = self._requests, {}
            external, self._external = self._external, {}
            errors, self._errors = self._errors, []
        if not (requests_ or external or errors):
            return

        hist_cols = ", ".join(HISTOGRAM_COLUMNS)
        hist_marks = ", ".join("?" for _ in HISTOGRAM_COLUMNS)
        hist_update = ", ".join(f"{c} = {c} + excluded.{c}" for c in HISTOGRAM_COLUMNS)
        try:
            conn = connect(db_path)
            try:
                conn.executemany(
                    f"""INSERT INTO request_metrics
                        (bucket, method, endpoint, count, errors_4xx, errors_5xx, total_ms, max_ms, {hist_cols})
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, {hist_marks})
                        ON CONFLICT(bucket, method, endpoint) DO UPDATE SET
                            count = count + excluded.count,
                            errors_4xx = errors_4xx + excluded.errors_4xx,
                            errors_5xx = errors_5xx + excluded.errors_5xx,
                            total_ms = total_ms + excluded.total_ms,
                            max_ms = MAX(max_ms, excluded.max_ms),
                            {hist_update}""",
                    [(b, m, e, s.count, s.errors_4xx, s.errors_5xx, s.total_ms, s.max_ms, *s.histogram)
                     for (b, m, e), s in requests_.items()],
                )
                conn.executemany(
                    f"""INSERT INTO external_metrics
                        (bucket, service, count, errors, total_ms, max_ms, {hist_cols})
                        VALUES (?, ?, ?, ?, ?, ?, {hist_marks})
                        ON CONFLICT(bucket, service) DO UPDATE SET
                            count = count + excluded.count,
                            errors = errors + excluded.errors,
                            total_ms = total_ms + excluded.total_ms,
                            max_ms = MAX(max_ms, excluded.max_ms),
                            {hist_update}""",
                    [(b, svc, s.count, s.errors_4xx + s.errors_5xx, s.total_ms, s.max_ms, *s.histogram)
                     for (b, svc), s in external.items()],
                )
                conn.executemany(
                    """INSERT INTO error_events
                        (ts, request_id, method, endpoint, path, status, error_type, message)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    errors,
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            # Drop this batch rather than grow memory unbounded
            logger.warning("Failed to flush monitoring metrics: %s", e)


collector = MetricsCollector()


def sample_resources() -> dict:
    """Collect one resource sample for the current process and host."""
    disk = shutil.disk_usage(str(webapp_config.BASE_DIR))
    sample = {
        "ts": int(time.time()),
        "pid": os.getpid(),
        "rss_mb": None,
        "cpu_percent": None,
        "threads": threading.active_count(),
        "open_fds": None,
        "sys_cpu_percent": None,
        "sys_mem_percent": None,
        "sys_mem_available_mb": None,
        "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
        "disk_percent": round(disk.used / disk.total * 100, 1),
        "disk_free_gb": round(disk.free / 1024 ** 3, 2),
    }
    if psutil is not None:
        proc = psutil.Process()
        with proc.oneshot():
            sample["rss_mb"] = round(proc.memory_info().rss / 1024 ** 2, 1)
            sample["cpu_percent"] = proc.cpu_percent(interval=None)
            sample["threads"] = proc.num_threads()
            if hasattr(proc, "num_fds"):
                sample["open_fds"] = proc.num_fds()
            elif hasattr(proc, "num_handles"):
                sample["open_fds"] = proc.num_handles()
        mem = psutil.virtual_memory()
        sample["sys_cpu_percent"] = psutil.cpu_percent(interval=None)
        sample["sys_mem_percent"] = mem.percent
        sample["sys_mem_available_mb"] = round(mem.available / 1024 ** 2, 1)
    return sample


def write_resource_sample(sample: dict, db_path=None) -> None:
    cols = list(sample.keys())
    conn = connect(db_path)
    try:
        conn.execute(
            f"INSERT INTO resource_samples ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [sample[c] for c in cols],
        )
        conn.commit()
    finally:
        conn.close()


def prune(db_path=None, days: int = RETENTION_DAYS) -> None:
    cutoff = int(time.time()) - days * 86400
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM request_metrics WHERE bucket < ?", (cutoff,))
        conn.execute("DELETE FROM external_metrics WHERE bucket < ?", (cutoff,))
        conn.execute("DELETE FROM resource_samples WHERE ts < ?", (cutoff,))
        conn.execute("DELETE FROM error_events WHERE ts < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()


# --- Background thread ------------------------------------------------------

_background_pid: int | None = None
_background_lock = threading.Lock()


def _background_loop() -> None:
    if psutil is not None:
        # Prime CPU counters; the first call always returns 0.0
        psutil.Process().cpu_percent(interval=None)
        psutil.cpu_percent(interval=None)
    last_sample = 0.0
    last_prune = 0.0
    while True:
        time.sleep(FLUSH_INTERVAL_S)
        now = time.time()
        try:
            collector.flush()
            if now - last_sample >= SAMPLE_INTERVAL_S:
                write_resource_sample(sample_resources())
                last_sample = now
            if now - last_prune >= 3600:
                prune()
                last_prune = now
        except Exception:
            logger.exception("Monitoring background loop iteration failed")


def ensure_background_thread() -> None:
    """Start the flush/sample thread once per process (gunicorn forks workers)."""
    global _background_pid
    pid = os.getpid()
    if _background_pid == pid:
        return
    with _background_lock:
        if _background_pid == pid:
            return
        threading.Thread(target=_background_loop, name="monitoring", daemon=True).start()
        atexit.register(collector.flush)
        _background_pid = pid


# --- Outbound HTTP instrumentation -----------------------------------------

_requests_patched = False


def instrument_requests() -> None:
    """Time every outbound ``requests`` call. Idempotent."""
    global _requests_patched
    if _requests_patched:
        return
    import requests

    original = requests.Session.request

    def timed_request(self, method, url, *args, **kwargs):
        start = time.perf_counter()
        status = None
        try:
            response = original(self, method, url, *args, **kwargs)
            status = response.status_code
            return response
        finally:
            ms = (time.perf_counter() - start) * 1000
            service = classify_service(str(url))
            collector.record_external(service, status, ms)
            if ms >= SLOW_REQUEST_MS:
                logger.warning("Slow outbound call: service=%s %s %s status=%s %.0fms",
                               service, method, urlparse(str(url)).path, status, ms)

    requests.Session.request = timed_request
    _requests_patched = True


# --- Flask integration ------------------------------------------------------

def _endpoint_label() -> str:
    rule = request.url_rule
    return rule.rule if rule is not None else "<unmatched>"


def init_monitoring(app: Flask) -> None:
    """Wire request timing, error capture and outbound instrumentation into the app."""
    try:
        init_db()
    except sqlite3.Error as e:
        logger.error("Failed to initialise monitoring DB: %s", e)

    instrument_requests()

    @app.before_request
    def _monitoring_start():
        g._monitoring_start = time.perf_counter()
        # Cloudflare's ray ID lets us correlate with CF logs; otherwise mint one
        g.request_id = request.headers.get("CF-Ray") or uuid.uuid4().hex[:16]
        if not app.testing:
            ensure_background_thread()

    @app.after_request
    def _monitoring_finish(response):
        start = g.pop("_monitoring_start", None)
        if start is None:
            return response
        ms = (time.perf_counter() - start) * 1000
        endpoint = _endpoint_label()
        collector.record_request(request.method, endpoint, response.status_code, ms)
        response.headers["X-Request-ID"] = g.request_id
        response.headers["Server-Timing"] = f"app;dur={ms:.1f}"
        if ms >= SLOW_REQUEST_MS:
            logger.warning("Slow request: %s %s status=%s %.0fms request_id=%s",
                           request.method, request.path, response.status_code, ms, g.request_id)
        if response.status_code >= 500 and not g.get("_monitoring_error_recorded"):
            collector.record_error(
                request_id=g.request_id, method=request.method, endpoint=endpoint,
                path=request.path, status=response.status_code, error_type="HTTP 5xx",
                message=response.get_data(as_text=True)[:MAX_ERROR_MESSAGE_LEN]
                if response.is_json else None,
            )
        return response

    def _on_exception(sender, exception, **extra):
        g._monitoring_error_recorded = True
        collector.record_error(
            request_id=g.get("request_id"), method=request.method, endpoint=_endpoint_label(),
            path=request.path, status=500, error_type=type(exception).__name__,
            message=str(exception),
        )

    got_request_exception.connect(_on_exception, app, weak=False)
