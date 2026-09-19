"""Geocoding for Explorer applications via OpenStreetMap Nominatim.

Nominatim is free and needs no API key, but it asks callers to identify
themselves and to stay under roughly one request per second. We only geocode
once per application (at submission, or on an explicit admin retry) and cache
the result on the row, so normal page loads never touch the service.
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim's usage policy requires a real identifying User-Agent.
USER_AGENT = "SummitSorceryBot/1.0 (Explorer Series application map)"

REQUEST_TIMEOUT_S = 10

# Nominatim allows ~1 request/second. Serialise calls and space them out.
_MIN_INTERVAL_S = 1.1
_rate_lock = threading.Lock()
_last_request_at = 0.0


def _throttle():
    global _last_request_at
    wait = _MIN_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def build_query(city: str | None, state: str | None, country: str | None) -> str:
    """Join the location parts an applicant gave us into a search string."""
    parts = [p.strip() for p in (city, state, country) if p and p.strip()]
    return ", ".join(parts)


def geocode_location(
    city: str | None, state: str | None, country: str | None = None
) -> tuple[float, float] | None:
    """Resolve a city/state/country to (latitude, longitude).

    Returns None when the location is blank, not found, or the service is
    unreachable — geocoding is best-effort and must never block a submission.
    """
    query = build_query(city, state, country)
    if not query:
        return None

    try:
        with _rate_lock:
            _throttle()
            response = requests.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_S,
            )
        response.raise_for_status()
        results = response.json()
    except Exception as exc:
        logger.warning("Geocoding failed for %r: %s", query, exc)
        return None

    if not results:
        logger.info("No geocoding result for %r", query)
        return None

    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Unexpected geocoding payload for %r: %s", query, exc)
        return None
