"""Read queries over the monitoring rollups written by ``utils.monitoring``."""

from __future__ import annotations

import time

from utils.monitoring import HISTOGRAM_COLUMNS, connect, percentile_from_histogram


def _step_for(hours: int) -> int:
    """Time-series resolution: ~100-300 points regardless of range."""
    if hours <= 1:
        return 60
    if hours <= 6:
        return 300
    if hours <= 24:
        return 900
    return 3600


def _latency_fields(row) -> dict:
    counts = [row[c] or 0 for c in HISTOGRAM_COLUMNS]
    count = row["count"] or 0
    return {
        "avg_ms": round(row["total_ms"] / count, 1) if count else None,
        "max_ms": round(row["max_ms"] or 0, 1),
        "p50_ms": percentile_from_histogram(counts, 0.50),
        "p95_ms": percentile_from_histogram(counts, 0.95),
        "p99_ms": percentile_from_histogram(counts, 0.99),
        "histogram": counts,
    }


class MonitoringRepository:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def _since(self, hours: float) -> int:
        return int(time.time() - hours * 3600)

    def _hist_sums(self) -> str:
        return ", ".join(f"SUM({c}) AS {c}" for c in HISTOGRAM_COLUMNS)

    def request_totals(self, hours: float) -> dict:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                f"""SELECT SUM(count) AS count, SUM(errors_4xx) AS errors_4xx,
                           SUM(errors_5xx) AS errors_5xx, SUM(total_ms) AS total_ms,
                           MAX(max_ms) AS max_ms, {self._hist_sums()}
                    FROM request_metrics WHERE bucket >= ?""",
                (self._since(hours),),
            ).fetchone()
        finally:
            conn.close()
        count = row["count"] or 0
        return {
            "count": count,
            "errors_4xx": row["errors_4xx"] or 0,
            "errors_5xx": row["errors_5xx"] or 0,
            "error_rate_5xx": round((row["errors_5xx"] or 0) / count * 100, 2) if count else 0,
            **_latency_fields(row),
        }

    def endpoint_summary(self, hours: float, limit: int = 100) -> list[dict]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                f"""SELECT method, endpoint, SUM(count) AS count,
                           SUM(errors_4xx) AS errors_4xx, SUM(errors_5xx) AS errors_5xx,
                           SUM(total_ms) AS total_ms, MAX(max_ms) AS max_ms, {self._hist_sums()}
                    FROM request_metrics WHERE bucket >= ?
                    GROUP BY method, endpoint
                    ORDER BY total_ms DESC LIMIT ?""",
                (self._since(hours), limit),
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "method": r["method"],
                "endpoint": r["endpoint"],
                "count": r["count"],
                "errors_4xx": r["errors_4xx"],
                "errors_5xx": r["errors_5xx"],
                "total_s": round(r["total_ms"] / 1000, 1),
                **_latency_fields(r),
            }
            for r in rows
        ]

    def external_summary(self, hours: float) -> list[dict]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                f"""SELECT service, SUM(count) AS count, SUM(errors) AS errors,
                           SUM(total_ms) AS total_ms, MAX(max_ms) AS max_ms, {self._hist_sums()}
                    FROM external_metrics WHERE bucket >= ?
                    GROUP BY service ORDER BY count DESC""",
                (self._since(hours),),
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "service": r["service"],
                "count": r["count"],
                "errors": r["errors"],
                "error_rate": round(r["errors"] / r["count"] * 100, 2) if r["count"] else 0,
                **_latency_fields(r),
            }
            for r in rows
        ]

    def traffic_timeseries(self, hours: float) -> list[dict]:
        step = _step_for(hours)
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                f"""SELECT bucket - (bucket % ?) AS t, SUM(count) AS count,
                           SUM(errors_4xx) AS errors_4xx, SUM(errors_5xx) AS errors_5xx,
                           SUM(total_ms) AS total_ms, MAX(max_ms) AS max_ms, {self._hist_sums()}
                    FROM request_metrics WHERE bucket >= ?
                    GROUP BY t ORDER BY t""",
                (step, self._since(hours)),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            lat = _latency_fields(r)
            out.append({
                "t": r["t"],
                "count": r["count"],
                "errors_4xx": r["errors_4xx"],
                "errors_5xx": r["errors_5xx"],
                "avg_ms": lat["avg_ms"],
                "p95_ms": lat["p95_ms"],
            })
        return out

    def resource_timeseries(self, hours: float) -> list[dict]:
        """Per-step totals across all worker processes (RSS/CPU summed, host metrics averaged)."""
        step = _step_for(hours)
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """SELECT t, COUNT(*) AS workers, SUM(rss_mb) AS rss_mb, SUM(cpu_percent) AS cpu_percent,
                          SUM(threads) AS threads, SUM(open_fds) AS open_fds,
                          AVG(sys_cpu_percent) AS sys_cpu_percent, AVG(sys_mem_percent) AS sys_mem_percent,
                          AVG(load_1m) AS load_1m, MAX(disk_percent) AS disk_percent
                   FROM (
                       SELECT ts - (ts % ?) AS t, pid, AVG(rss_mb) AS rss_mb, AVG(cpu_percent) AS cpu_percent,
                              MAX(threads) AS threads, MAX(open_fds) AS open_fds,
                              AVG(sys_cpu_percent) AS sys_cpu_percent, AVG(sys_mem_percent) AS sys_mem_percent,
                              AVG(load_1m) AS load_1m, MAX(disk_percent) AS disk_percent
                       FROM resource_samples WHERE ts >= ?
                       GROUP BY t, pid
                   ) GROUP BY t ORDER BY t""",
                (step, self._since(hours)),
            ).fetchall()
        finally:
            conn.close()
        return [
            {k: (round(r[k], 1) if isinstance(r[k], float) else r[k]) for k in r.keys()}
            for r in rows
        ]

    def latest_resources(self, max_age_s: int = 180) -> dict | None:
        """Most recent sample per live worker, aggregated."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """SELECT s.* FROM resource_samples s
                   JOIN (SELECT pid, MAX(ts) AS ts FROM resource_samples WHERE ts >= ? GROUP BY pid) latest
                     ON s.pid = latest.pid AND s.ts = latest.ts""",
                (int(time.time()) - max_age_s,),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            return None
        newest = max(rows, key=lambda r: r["ts"])
        return {
            "ts": newest["ts"],
            "workers": [
                {"pid": r["pid"], "rss_mb": r["rss_mb"], "cpu_percent": r["cpu_percent"],
                 "threads": r["threads"], "open_fds": r["open_fds"]}
                for r in sorted(rows, key=lambda r: r["pid"])
            ],
            "total_rss_mb": round(sum(r["rss_mb"] or 0 for r in rows), 1),
            "sys_cpu_percent": newest["sys_cpu_percent"],
            "sys_mem_percent": newest["sys_mem_percent"],
            "sys_mem_available_mb": newest["sys_mem_available_mb"],
            "load_1m": newest["load_1m"],
            "disk_percent": newest["disk_percent"],
            "disk_free_gb": newest["disk_free_gb"],
        }

    def recent_errors(self, hours: float, limit: int = 50) -> list[dict]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """SELECT ts, request_id, method, endpoint, path, status, error_type, message
                   FROM error_events WHERE ts >= ? ORDER BY ts DESC LIMIT ?""",
                (self._since(hours), limit),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]
