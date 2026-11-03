"""Staple cards: the cards that are both widely played and pull their weight.

Built on the same Play Sorcery Online ranked card rows as the Card Win Rates
page (``services/ranked_analytics``). PSO fixes the population there (first
games at Summit matchmade ranked tables) and only answers through its
release cutoff, so this only ever sees released batch data. Every number
here is an aggregate over many games; no deck list or player is exposed.

Staple score (0-100), worked out over the eligible cards in the window:

    50%  Popularity   deck share (how many decks run it)
    30%  Impact       played win rate minus "in deck, not played" win rate
                      (the page's "Played vs. not played" column), pulled
                      toward 0 when the smaller of the two samples is small
    20%  Win rate     in-deck win rate, pulled toward 50% for small samples

Each part is turned into a percentile (0-100) among the eligible cards
before weighting, so a share of 40% and a swing of +8 points are comparable.
Avatars are left out (every deck has exactly one), and a card needs
``min_games`` in-deck games to be eligible at all.
"""

import logging
import threading
import time
from datetime import date, timedelta

from services import ranked_analytics

logger = logging.getLogger(__name__)

WEIGHTS = {"popularity": 0.5, "impact": 0.3, "win_rate": 0.2}
DEFAULT_LIMIT = 100
MAX_LIMIT = 100
DEFAULT_MIN_GAMES = 50
DEFAULT_DAYS = 90
# Games of "prior" used to shrink small samples toward neutral.
IMPACT_PRIOR_GAMES = 50
WIN_RATE_PRIOR_GAMES = 50
# Both sides of the played / not played split need this many games
# before the swing counts; otherwise the card's impact is neutral (0).
MIN_SPLIT_GAMES = 20

CACHE_TTL_SECONDS = 600
_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


class StaplesUnavailable(Exception):
    """PSO card data could not be fetched."""


def _games(rate: dict | None) -> int:
    value = (rate or {}).get("playerGames")
    return int(value) if isinstance(value, (int, float)) and value > 0 else 0


def _rate(rate: dict | None) -> float | None:
    value = (rate or {}).get("winRate")
    return float(value) if isinstance(value, (int, float)) else None


def _wins(rate: dict | None) -> float:
    rate = rate or {}
    if isinstance(rate.get("wins"), (int, float)):
        return float(rate["wins"])
    win_rate, games = _rate(rate), _games(rate)
    return win_rate * games if win_rate is not None else 0.0


def _percentiles(values: list[float]) -> list[float]:
    """Percentile rank (0-100) of each value; ties share the average rank."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [100.0]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2
        for k in range(i, j + 1):
            ranks[order[k]] = average / (n - 1) * 100
        i = j + 1
    return ranks


def _pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100, 1)


def score_cards(body: dict, catalog: list[dict], *, min_games: int = DEFAULT_MIN_GAMES) -> list[dict]:
    """Every eligible card with its staple score, best first."""
    meta = {}
    for entry in catalog or []:
        name = (entry.get("name") or "").strip().lower()
        if name and name not in meta:
            meta[name] = entry

    rows = []
    for card in (body or {}).get("cards") or []:
        name = card.get("cardName") or card.get("cardKey")
        if not name:
            continue
        info = meta.get(name.strip().lower()) or meta.get((card.get("cardKey") or "").lower()) or {}
        if (info.get("type") or "").lower() == "avatar":
            continue
        in_deck, played, unplayed = card.get("inDeck"), card.get("played"), card.get("inDeckUnplayed")
        deck_games = _games(in_deck)
        share = card.get("deckShare")
        if deck_games < min_games or not isinstance(share, (int, float)):
            continue

        played_rate, unplayed_rate = _rate(played), _rate(unplayed)
        split = min(_games(played), _games(unplayed))
        swing = None
        impact = 0.0
        if played_rate is not None and unplayed_rate is not None:
            swing = played_rate - unplayed_rate
            if split >= MIN_SPLIT_GAMES:
                impact = swing * split / (split + IMPACT_PRIOR_GAMES)
        win_adjusted = (_wins(in_deck) + 0.5 * WIN_RATE_PRIOR_GAMES) / (deck_games + WIN_RATE_PRIOR_GAMES)

        rows.append({
            "name": name,
            "cardKey": card.get("cardKey") or name.lower(),
            "type": info.get("type") or None,
            "elements": list(info.get("elements") or []),
            "rarity": info.get("rarity") or None,
            "imageUrl": info.get("imageUrl"),
            "deckShare": float(share),
            "inDeckWinRate": _rate(in_deck),
            "playedWinRate": played_rate,
            "notPlayedWinRate": unplayed_rate,
            "swing": swing,
            "openingHandWinRate": _rate(card.get("openingHand")),
            "games": {
                "inDeck": deck_games,
                "played": _games(played),
                "notPlayed": _games(unplayed),
                "openingHand": _games(card.get("openingHand")),
            },
            "_impact": impact,
            "_win": win_adjusted,
        })

    pop = _percentiles([r["deckShare"] for r in rows])
    imp = _percentiles([r["_impact"] for r in rows])
    win = _percentiles([r["_win"] for r in rows])
    for row, p, i, w in zip(rows, pop, imp, win):
        row["components"] = {"popularity": round(p, 1), "impact": round(i, 1), "win_rate": round(w, 1)}
        row["stapleScore"] = round(
            WEIGHTS["popularity"] * p + WEIGHTS["impact"] * i + WEIGHTS["win_rate"] * w, 1
        )
    rows.sort(key=lambda r: (-r["stapleScore"], -r["deckShare"], r["name"]))
    return rows


def _public(row: dict, rank: int, site: str) -> dict:
    image = row["imageUrl"]
    if isinstance(image, str) and image.startswith("/"):
        image = f"{site}{image}"
    return {
        "rank": rank,
        "name": row["name"],
        "cardKey": row["cardKey"],
        "type": row["type"],
        "elements": row["elements"],
        "rarity": row["rarity"],
        "imageUrl": image,
        "stapleScore": row["stapleScore"],
        "components": row["components"],
        "deckShare": _pct(row["deckShare"]),
        "inDeckWinRate": _pct(row["inDeckWinRate"]),
        "playedWinRate": _pct(row["playedWinRate"]),
        "notPlayedWinRate": _pct(row["notPlayedWinRate"]),
        "playedVsNotPlayed": _pct(row["swing"]),
        "openingHandWinRate": _pct(row["openingHandWinRate"]),
        "games": row["games"],
    }


def _breakdown(rows: list[dict]) -> dict:
    by_type, by_element, by_rarity = {}, {}, {}
    for row in rows:
        by_type[row["type"] or "Unknown"] = by_type.get(row["type"] or "Unknown", 0) + 1
        elements = [e for e in row["elements"] if e and e.lower() != "none"]
        key = "None" if not elements else ("Multi" if len(elements) > 1 else elements[0])
        by_element[key] = by_element.get(key, 0) + 1
        by_rarity[row["rarity"] or "Unknown"] = by_rarity.get(row["rarity"] or "Unknown", 0) + 1

    def ordered(counts):
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    return {"type": ordered(by_type), "element": ordered(by_element), "rarity": ordered(by_rarity)}


def resolve_window(season: str | None, from_: str | None, through: str | None,
                   today: date | None = None) -> dict:
    """The date range to ask PSO for.

    ``season=all`` is all time, ``season=<id>`` a Summit season's dates,
    ``from``/``through`` an explicit range. With none of those, the last
    DEFAULT_DAYS days (PSO still stops at its release cutoff).
    """
    if season:
        if season == "all":
            return {"label": "All time", "from": None, "through": None}
        for entry in ranked_analytics.list_seasons():
            if entry["id"] == season:
                return {"label": entry["name"], "from": entry["from"], "through": entry["through"]}
        raise ValueError("Unknown season")
    if from_ or through:
        return {"label": "Custom", "from": from_, "through": through}
    today = today or date.today()
    return {"label": f"Last {DEFAULT_DAYS} days",
            "from": (today - timedelta(days=DEFAULT_DAYS)).isoformat(), "through": None}


def _fetch(window: dict) -> dict:
    key = (window["from"], window["through"])
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    params = {"format": "constructed"}
    if window["from"]:
        params["from"] = window["from"]
    if window["through"]:
        params["through"] = window["through"]
    try:
        result = ranked_analytics.forward("GET", "cards", params=params)
    except ranked_analytics.AnalyticsUnavailable as exc:
        raise StaplesUnavailable(str(exc))
    if result.status != 200 or not isinstance(result.body, dict):
        raise StaplesUnavailable("Card data is unavailable")
    with _cache_lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = (now, result.body)
    return result.body


def get_staples(window: dict, *, limit: int = DEFAULT_LIMIT, min_games: int = DEFAULT_MIN_GAMES,
                card_type: str | None = None, element: str | None = None) -> dict:
    body = _fetch(window)
    if body.get("dataAvailable") is False:
        raise StaplesUnavailable("Card data is not available yet")
    rows = score_cards(body, ranked_analytics.build_catalog(), min_games=min_games)
    eligible = len(rows)
    if card_type:
        rows = [r for r in rows if (r["type"] or "").lower() == card_type.lower()]
    if element:
        wanted = element.lower()

        def matches(r):
            elements = {e.lower() for e in r["elements"] if e and e.lower() != "none"}
            if wanted == "none":
                return not elements
            if wanted == "multi":
                return len(elements) > 1
            return wanted in elements

        rows = [r for r in rows if matches(r)]
    rows = rows[:limit]

    from services.meta_report import site_url

    site = site_url()
    return {
        "window": {"label": window["label"], "from": window["from"], "through": window["through"]},
        "releasedThrough": body.get("releasedThrough"),
        "totalGames": body.get("totalGames"),
        "eligibleCards": eligible,
        "minGames": min_games,
        "formula": {
            "weights": WEIGHTS,
            "popularity": "deck share percentile",
            "impact": "percentile of (played win rate - in deck, not played win rate), "
                      f"shrunk toward 0 with {IMPACT_PRIOR_GAMES} games of prior; "
                      f"needs {MIN_SPLIT_GAMES}+ games on each side",
            "win_rate": f"percentile of in-deck win rate, shrunk toward 50% with {WIN_RATE_PRIOR_GAMES} games of prior",
            "excluded": "avatars; cards under minGames in-deck games",
        },
        "breakdown": _breakdown(rows),
        "count": len(rows),
        "cards": [_public(row, i + 1, site) for i, row in enumerate(rows)],
    }


def reset_cache() -> None:
    """For tests."""
    with _cache_lock:
        _cache.clear()
