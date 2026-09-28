"""Server-side proxy for Play Sorcery Online's Summit ranked analytics.

The Card Win Rates page calls ``/api/ranked-analytics/*`` on this server. This
module forwards those calls to PSO's partner routes with the shared
integration key, which must never reach a browser::

    browser -> /api/ranked-analytics/cards -> PSO /api/summit/game-analytics/cards
                                              X-API-Key: DRAFT_SORCERY_API_KEY

PSO enforces the population (first games at Summit matchmade ranked tables)
and the release cutoff on its side, so there is nothing to compute here. The
proxy's job is to keep the key private, allow only the four read-only routes,
forward only the selection parameters PSO accepts, and hide upstream error
details from the browser.

The partner route is switched on by PSO. Until then every call answers 503
and the page shows its "not available yet" state.
"""

import logging
import os
import re
import threading
import time
from typing import NamedTuple

import requests

import webapp_config
from repositories.card_catalog import CardCatalogRepository
from utils.card_images import resolve_card_image

logger = logging.getLogger(__name__)

DEFAULT_UPSTREAM = "https://playsorceryonline.com/api/summit/game-analytics"
# (connect, read). Cohort queries scan a lot of games upstream.
REQUEST_TIMEOUT_S = (3, 30)
MAX_BODY_BYTES = 16 * 1024
# Summit only runs constructed ranked queues. PSO would accept "limited"
# too, but nothing on the site asks for it.
FORMATS = ("constructed",)
SELECTION_KEYS = ("format", "from", "through")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CARD_KEY_RE = re.compile(r"^[^/\\]{1,120}$")

# Per-client request budget. This is a public endpoint that spends PSO's
# capacity under our key, so a runaway client is cut off before it becomes
# PSO's problem. In-process only, like the Try this Deck cooldown.
WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 60
_MAX_TRACKED_CLIENTS = 5000
_client_hits: dict[str, list[float]] = {}
_client_lock = threading.Lock()

CATALOG_TTL_SECONDS = 600
_catalog_cache: tuple[float, list[dict]] | None = None
_catalog_lock = threading.Lock()

# PSO's public card list. Our own card_catalog table comes from the Curiosa
# feed, which carries no avatars, so avatar rows, the Avatar quick filter and
# the replay portraits would all be blank without this. Public, no key.
PSO_CATALOG_URL = "https://playsorceryonline.com/api/catalog/cards"
PSO_IMAGE_BASE = "https://playsorceryonline.com"
PSO_CATALOG_TTL_SECONDS = 24 * 3600
PSO_CATALOG_RETRY_SECONDS = 600
_pso_catalog_cache: tuple[float, list[dict]] | None = None


class ProxyResult(NamedTuple):
    status: int
    body: dict | list


class AnalyticsUnavailable(Exception):
    """PSO could not answer; the browser gets a generic 503."""


class InvalidSelection(ValueError):
    """The caller asked for something PSO would reject; answer 400."""


def upstream_base() -> str:
    return os.getenv("SORCERY_ONLINE_ANALYTICS_URL", DEFAULT_UPSTREAM).strip().rstrip("/")


def is_configured() -> bool:
    return bool((webapp_config.DRAFT_SORCERY_API_KEY or "").strip() and upstream_base())


def claim_request(client_key: str) -> bool:
    """Record one request for this client. False when they are over budget."""
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS
    with _client_lock:
        hits = _client_hits.get(client_key)
        if hits is None:
            if len(_client_hits) >= _MAX_TRACKED_CLIENTS:
                for key in [k for k, ts in _client_hits.items() if not ts or ts[-1] < cutoff]:
                    del _client_hits[key]
                if len(_client_hits) >= _MAX_TRACKED_CLIENTS:
                    _client_hits.clear()
            hits = _client_hits[client_key] = []
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= MAX_REQUESTS_PER_WINDOW:
            return False
        hits.append(now)
    return True


def clean_selection(args) -> dict[str, str]:
    """Keep only ``format``, ``from`` and ``through``, each given once and well formed.

    PSO rejects any other parameter (game type, provider, admin overrides), so
    they are refused here rather than forwarded and logged upstream.
    """
    selection: dict[str, str] = {}
    for key in args.keys():
        if key not in SELECTION_KEYS:
            raise InvalidSelection(f"Unexpected parameter: {key}")
        values = args.getlist(key)
        if len(values) != 1:
            raise InvalidSelection(f"Parameter given more than once: {key}")
        selection[key] = values[0].strip()

    fmt = selection.get("format")
    if fmt not in FORMATS:
        raise InvalidSelection("format must be 'constructed'")
    for key in ("from", "through"):
        value = selection.get(key)
        if value is not None and not _DATE_RE.match(value):
            raise InvalidSelection(f"{key} must be a YYYY-MM-DD date")
    return selection


def validate_card_key(card_key: str) -> str:
    if not card_key or not _CARD_KEY_RE.match(card_key):
        raise InvalidSelection("Invalid card key")
    return card_key


def forward(method: str, route: str, *, params: dict | None = None, body: bytes | None = None) -> ProxyResult:
    """Send one request to PSO and return the JSON body to relay.

    Upstream 400s become our 400 with a generic message. Anything else that
    is not a 200 (auth failures, 404 while the route is disabled, 5xx) is a
    503 to the browser; the real status is logged without headers.
    """
    api_key = (webapp_config.DRAFT_SORCERY_API_KEY or "").strip()
    base = upstream_base()
    if not api_key or not base:
        raise AnalyticsUnavailable("Ranked analytics is not configured")

    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        response = requests.request(
            method,
            f"{base}/{route}",
            params=params or None,
            data=body,
            headers=headers,
            timeout=REQUEST_TIMEOUT_S,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        logger.warning("Ranked analytics request failed: %s %s: %r", method, route, exc)
        raise AnalyticsUnavailable("Could not reach Play Sorcery Online")

    if response.status_code == 400:
        logger.info("Ranked analytics rejected a query: %s %s: %s", method, route, response.text[:300])
        return ProxyResult(400, {"error": "Invalid analytics query"})
    if response.status_code != 200:
        logger.warning(
            "Ranked analytics upstream returned %s for %s %s: %s",
            response.status_code, method, route, response.text[:300],
        )
        raise AnalyticsUnavailable("Ranked analytics is unavailable")
    try:
        payload = response.json()
    except ValueError:
        logger.warning("Ranked analytics upstream sent non-JSON for %s %s", method, route)
        raise AnalyticsUnavailable("Ranked analytics returned an unexpected response")
    if not isinstance(payload, (dict, list)):
        raise AnalyticsUnavailable("Ranked analytics returned an unexpected response")
    return ProxyResult(200, payload)


def fetch_pso_catalog() -> list[dict]:
    """PSO's public card list, one entry per card name, cached for a day.

    A failed fetch is remembered for a few minutes so a PSO outage does not
    turn every catalog request into a slow outbound call. Returns [] then.
    """
    global _pso_catalog_cache
    now = time.monotonic()
    with _catalog_lock:
        if _pso_catalog_cache:
            fetched_at, cards = _pso_catalog_cache
            ttl = PSO_CATALOG_TTL_SECONDS if cards else PSO_CATALOG_RETRY_SECONDS
            if now - fetched_at < ttl:
                return cards
    cards: list[dict] = []
    try:
        response = requests.get(PSO_CATALOG_URL, timeout=(3, 15), headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("catalog is not a list")
        seen: set[str] = set()
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            elements = entry.get("elements")
            image = entry.get("imageUrl")
            cards.append({
                "name": name,
                "type": str(entry.get("type") or ""),
                "elements": [str(e) for e in elements if e] if isinstance(elements, list) else [],
                "rarity": str(entry.get("rarity") or ""),
                "imageUrl": f"{PSO_IMAGE_BASE}{image}" if isinstance(image, str) and image.startswith("/") else None,
            })
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not fetch the Play Sorcery Online card catalog: %r", exc)
        cards = []
    with _catalog_lock:
        _pso_catalog_cache = (now, cards)
    return cards


def build_catalog() -> list[dict]:
    """Card metadata in the shape the analytics UI wants, cached for a while.

    ``{name, type, elements: [...], rarity, imageUrl}`` per card. Our own
    ``card_catalog`` rows come first; elements there are a comma list and
    ``None`` becomes an empty list so the UI's "None" and "Multi" filters
    work. Names it lacks (avatars, mostly) are filled in from PSO's public
    catalog. Images come from the local folder every other deck view uses,
    falling back to PSO's own image for cards we have no art for.
    """
    global _catalog_cache
    now = time.monotonic()
    with _catalog_lock:
        if _catalog_cache and now - _catalog_cache[0] < CATALOG_TTL_SECONDS:
            return _catalog_cache[1]
    cards = []
    seen: set[str] = set()
    try:
        rows = CardCatalogRepository().get_all_cards()
    except Exception as exc:
        logger.error("Could not load the card catalog for analytics: %s", exc)
        rows = []
    pso_by_name = {entry["name"].lower(): entry for entry in fetch_pso_catalog()}
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        raw_elements = (row.get("elements") or "").strip()
        elements = [] if raw_elements.lower() in ("", "none") else [
            e.strip() for e in raw_elements.split(",") if e.strip()
        ]
        # The synced table can carry a name with no metadata at all (the
        # production copy does, for every row). PSO's list fills the gaps so
        # the type, element and rarity filters still work.
        pso = pso_by_name.get(name.lower())
        card_type = row.get("card_type") or (pso["type"] if pso else "")
        rarity = row.get("rarity") or (pso["rarity"] if pso else "")
        if not elements and raw_elements.lower() != "none" and pso:
            elements = list(pso["elements"])
        image = resolve_card_image(name)
        cards.append({
            "name": name,
            "type": card_type,
            "elements": elements,
            "rarity": rarity,
            "imageUrl": f"/card-images/{image}" if image else (pso["imageUrl"] if pso else None),
        })
    for key, entry in pso_by_name.items():
        if key in seen:
            continue
        seen.add(key)
        image = resolve_card_image(entry["name"])
        cards.append(dict(entry, imageUrl=f"/card-images/{image}" if image else entry["imageUrl"]))
    with _catalog_lock:
        _catalog_cache = (now, cards)
    return cards


def reset_caches() -> None:
    """For tests."""
    global _catalog_cache, _pso_catalog_cache
    with _catalog_lock:
        _catalog_cache = None
        _pso_catalog_cache = None
    with _client_lock:
        _client_hits.clear()
