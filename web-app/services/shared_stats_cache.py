"""Shared, file-backed cache for stats that read every reported decklist.

Parsing every deck takes many seconds, so it must never run per request.
A result is built by one worker at a time (a lock file), saved to a shared
cache file and read from there by the other workers, so a worker that has just
restarted picks it up without rebuilding. Inside a worker a stale copy keeps
being served while one background thread refreshes it; only a visit with no
copy at all (memory or file) waits, and concurrent visits wait on the same
build.

Same pattern as the Elements timeline cache in routes/api/cards.py.
"""
import fcntl
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(tempfile.gettempdir()) / "summit-web-cache"

_registry = []


class StatsBuilding(Exception):
    """The first build is still running after the wait limit."""


class SharedStatsCache:
    def __init__(self, name, version, ttl, wait=90, max_keys=16):
        self.name = name
        self.version = version  # bump when the build's output changes
        self.ttl = ttl
        self.wait = wait  # seconds a first visit waits (gunicorn timeout is 120)
        self.max_keys = max_keys
        self._mem = {}  # key -> (built_at, data)
        self._builds = {}  # key -> threading.Event set when its build ends
        self._lock = threading.Lock()
        _registry.append(self)

    # -- files ---------------------------------------------------------------
    def _path(self, key):
        digest = hashlib.sha1(json.dumps(key, default=str).encode()).hexdigest()[:20]
        return CACHE_DIR / f"{self.name}-v{self.version}-{digest}.json"

    def _fresh_file(self, path):
        try:
            built_at = path.stat().st_mtime
            if time.time() - built_at >= self.ttl:
                return None
            with open(path, "r", encoding="utf-8") as f:
                return built_at, json.load(f)
        except (OSError, ValueError):
            return None

    def _load_or_build(self, key, build):
        path = self._path(key)
        fresh = self._fresh_file(path)
        if fresh:
            return fresh
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_suffix(".lock"), "w") as lock:
            # Waits while another worker builds the same key, then uses its result.
            fcntl.flock(lock, fcntl.LOCK_EX)
            fresh = self._fresh_file(path)
            if fresh:
                return fresh
            data = build()
            if data is None:
                return None
            tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp, path)
            except OSError as e:
                logger.warning(f"Could not write {self.name} cache: {e}")
            return time.time(), data

    # -- memory + background refresh -----------------------------------------
    def _refresh(self, key, build, done):
        try:
            result = self._load_or_build(key, build)
            if result is not None:
                with self._lock:
                    self._mem[key] = result
                    while len(self._mem) > self.max_keys:
                        oldest = min(self._mem, key=lambda k: self._mem[k][0])
                        del self._mem[oldest]
        except Exception as e:  # keep serving the stale copy
            logger.warning(f"{self.name} rebuild failed for {key}: {e}")
        finally:
            with self._lock:
                self._builds.pop(key, None)
            done.set()

    def _start(self, key, build):
        """The in-flight build for this key, starting one if none is running.

        Caller holds self._lock.
        """
        done = self._builds.get(key)
        if done is None:
            done = self._builds[key] = threading.Event()
            threading.Thread(target=self._refresh, args=(key, build, done),
                             name=f"{self.name}-cache", daemon=True).start()
        return done

    def get(self, key, build):
        """Cached data for key, building it with build() when needed.

        Returns None when the build failed and nothing is cached; raises
        StatsBuilding when the first build is still running after the wait.
        """
        with self._lock:
            hit = self._mem.get(key)
            done = None
            if hit is None or time.time() - hit[0] >= self.ttl:
                done = self._start(key, build)
        if hit is not None:
            return hit[1]
        finished = done.wait(self.wait)
        with self._lock:
            hit = self._mem.get(key)
        if hit is not None:
            return hit[1]
        if not finished:
            raise StatsBuilding()
        return None

    def warm(self, key, build):
        """Start loading or building key in the background (worker start)."""
        with self._lock:
            if key not in self._mem:
                self._start(key, build)

    def clear(self):
        with self._lock:
            self._mem.clear()
            self._builds.clear()


def clear_all():
    for cache in _registry:
        cache.clear()
