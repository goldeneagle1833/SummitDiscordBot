"""What each MCP tool does, kept apart from the MCP wiring so it is easy to test.

Every function takes a ``SiteClient`` and returns plain JSON-able data.
Rules (see safety.py):
  - Only the Top 8 tools may return deck links, and only to Top 8 decks on
    our own site (/deck-rec/<id>). Everything else goes through ``safe``.
  - No leaderboard, no ranks and no ratings for players (Bruce, 2026-11-27).
  - Card numbers come from the saved release snapshots only; a custom date
    range would make the site ask Play Sorcery Online, so it is never sent.
"""

from __future__ import annotations

import re
from urllib.parse import quote
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .safety import compact, safe
from .site_client import PUBLIC_URL, SignInExpired, SiteClient, SiteError

ELEMENTS = ("Air", "Earth", "Fire", "Water")
SLOW_TTL = 30 * 60  # pages the site itself rebuilds rarely
EVENT_TTL = 60 * 60

_SEASONS = {"current": "current", "season": "current", "this season": "current",
            "all": "all", "lifetime": "all", "all time": "all"}


def _season(value: str | None) -> str:
    return _SEASONS.get((value or "current").strip().lower(), "current")


def _link(path: str) -> str:
    return PUBLIC_URL + quote(path, safe="/?=&")


def _pct(wins: int, games: int) -> float | None:
    return round(wins / games * 100, 1) if games else None


# ----------------------------------------------------------------------
# Name matching helpers
# ----------------------------------------------------------------------


async def _avatar_names(site: SiteClient) -> list[str]:
    """Avatar names from the card pool (cached by the Deck Builder) plus this season's list.

    The all-time /api/avatars page takes ~20 s to build, so it is never used
    just to check a name.
    """
    names: set[str] = set()
    try:
        cards = await site.get(site.path("deck-builder", "all-cards"), ttl=24 * 60 * 60)
        names |= {str(c.get("name")) for c in cards or []
                  if isinstance(c, dict) and str(c.get("type", "")).lower() == "avatar" and c.get("name")}
    except SiteError:
        pass
    try:
        rows = await site.get(site.path("avatars", event="current"), ttl=SLOW_TTL)
        names |= {r["name"] for r in rows or [] if isinstance(r, dict) and r.get("name")}
    except SiteError:
        pass
    return sorted(names)


async def _resolve_avatar(site: SiteClient, name: str) -> str:
    wanted = (name or "").strip()
    if not wanted:
        raise SiteError("Please name an Avatar.")
    names = await _avatar_names(site)
    lowered = wanted.lower()
    for candidate in names:
        if candidate.lower() == lowered:
            return candidate
    close = [c for c in names if lowered in c.lower() or c.lower() in lowered]
    if len(close) == 1:
        return close[0]
    if names and not close:
        raise SiteError(f"No Avatar called '{wanted}'. Known Avatars: {', '.join(names)}.")
    return wanted


# ----------------------------------------------------------------------
# Player lookup
# ----------------------------------------------------------------------


async def _find_player(site: SiteClient, player: str) -> tuple[dict | None, dict | None]:
    """(chosen search row, None) or (None, a not-found answer to return as is)."""
    query = (player or "").strip()
    if len(query) < 2:
        raise SiteError("Please give at least two letters of the player's name.")
    found = (await site.get(site.path("players", "search", q=query, limit=5))).get("players") or []
    if not found:
        return None, {"found": False, "message": f"No Summit player matches '{query}'."}
    exact = [p for p in found if str(p.get("display_name", "")).lower() == query.lower()]
    if not exact and len(found) > 1:
        return None, {"found": False, "message": "Several players match; ask again with one of these names.",
                      "matches": [p.get("display_name") for p in found]}
    return (exact or found)[0], None


async def player_lookup(site: SiteClient, player: str, season: str = "current") -> dict:
    chosen, missing = await _find_player(site, player)
    if missing:
        return missing
    player_id = str(chosen["user_id"])
    event = "current" if _season(season) == "current" else "lifetime"
    data = await site.get(site.path("player", player_id, event=event))

    wins, losses = int(data.get("wins") or 0), int(data.get("losses") or 0)
    recent = []
    for m in (data.get("matches") or [])[:10]:
        recent.append({
            "date": str(m.get("date") or "")[:10],
            "result": m.get("result"),
            "opponent": m.get("opponent"),
            "avatar": m.get("player_avatar"),
            "opponent_avatar": m.get("opponent_avatar"),
        })
    avatars = [
        {"avatar": a.get("name"), "wins": a.get("wins"), "losses": a.get("losses"), "win_rate": a.get("win_rate")}
        for a in data.get("avatar_performance") or []
    ]
    against = [
        {"opponent_avatar": a.get("opponent_avatar"), "wins": a.get("wins"), "losses": a.get("losses"),
         "win_rate": a.get("win_rate")}
        for a in data.get("avatar_matchups") or []
    ]
    result = {
        "found": True,
        "player": data.get("name") or chosen.get("display_name"),
        "period": "this season" if event == "current" else "all seasons",
        "ranked_record": {"wins": wins, "losses": losses, "games": wins + losses, "win_rate": _pct(wins, wins + losses)},
        "going_first_win_rate": data.get("on_play_win_rate"),
        "going_second_win_rate": data.get("on_draw_win_rate"),
        "avatars_played": avatars,
        "results_against_avatars": against,
        "recent_ranked_games": recent,
        "profile": _link(f"/player/{player_id}"),
        "note": "Sections the player keeps private on their profile are left out.",
    }
    return safe(result)


# ----------------------------------------------------------------------
# Match history review
# ----------------------------------------------------------------------

MCP_SITE = "https://sorcererssummit.com/mcp"  # the public match API asks every caller to name itself
REVIEW_MAX_GAMES = 300
REVIEW_MIN_GAMES = 3  # a group needs this many games to be listed


def _bucket(rows: dict, key: str | None, won: bool) -> None:
    if not key:
        return
    row = rows.setdefault(key, [0, 0])
    row[0 if won else 1] += 1


def _table(rows: dict, label: str, min_games: int = REVIEW_MIN_GAMES) -> list[dict]:
    out = [{label: k, "wins": w, "losses": l, "games": w + l, "win_rate": _pct(w, w + l)}
           for k, (w, l) in rows.items() if w + l >= min_games]
    out.sort(key=lambda r: (-r["games"], r[label]))
    return out


def _elements(value) -> str | None:
    return " / ".join(value) if value else None


def _length_bucket(minutes) -> str | None:
    try:
        minutes = float(minutes)
    except (TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    if minutes < 15:
        return "under 15 min"
    if minutes < 30:
        return "15-30 min"
    return "30+ min"


async def _latest_report(site: SiteClient) -> tuple[str | None, dict | None]:
    try:
        listing = (await site.get(site.path("meta-reports"), ttl=SLOW_TTL)).get("reports") or []
        if not listing:
            return None, None
        report = await site.get(site.path("meta-reports", listing[0]["slug"]), ttl=SLOW_TTL)
        return listing[0].get("label") or listing[0]["slug"], report
    except SiteError:
        return None, None


async def match_history_review(site: SiteClient, player: str, season: str = "all") -> dict:
    """Everything an AI needs to coach a player from their ranked games.

    Reads the public match history API (avatar + deck elements per game only,
    never a deck list). Ratings and opponent names are left out: tips are about
    the player's own play, not about other people or rank.
    """
    chosen, missing = await _find_player(site, player)
    if missing:
        return missing
    player_id = str(chosen["user_id"])
    event = _season(season)
    matches, released_through = await _collect_matches(
        site, lambda page: site.path("public", "players", player_id, "matches",
                                     season=event, page=page, per_page=100, site=MCP_SITE))
    result = await _review(site, matches, chosen.get("display_name"), event, released_through,
                           _link(f"/player/{player_id}"))
    if result.get("found"):
        result["deeper_review"] = (
            "This review uses public data only. For a deeper one with the player's private Card Stats "
            "and this season's newest games, they can add the signed-in connector "
            f"{PUBLIC_URL}/mcp/account in their AI app and sign in with any Summit login "
            "(Discord, Google or an email code). Offer this to the player.")
    return result


async def _collect_matches(site: SiteClient, page_path, user_token: str | None = None) -> tuple[list[dict], Any]:
    matches: list[dict] = []
    released_through = None
    page = 1
    while len(matches) < REVIEW_MAX_GAMES:
        data = await site.get(page_path(page), allow_404=True, user_token=user_token)
        if not data:
            break
        released_through = data.get("deck_info_released_through") or released_through
        matches.extend(m for m in data.get("matches") or [] if isinstance(m, dict))
        if not (data.get("pagination") or {}).get("has_next"):
            break
        page += 1
    return matches[:REVIEW_MAX_GAMES], released_through


async def _review(site: SiteClient, matches: list[dict], name, event: str, released_through, profile: str) -> dict:
    period = "this season" if event == "current" else f"last {len(matches)} ranked games"
    if not matches:
        return {"found": True, "player": name, "period": period, "games": 0,
                "message": f"{name} has no ranked games {'this season' if event == 'current' else ''} yet."
                .replace("  ", " ")}

    wins = sum(1 for m in matches if m.get("result") == "win")
    by_avatar, by_elements, vs_avatar, vs_elements = {}, {}, {}, {}
    play, length, main_vs = {}, {}, {}
    with_deck = [m for m in matches if (m.get("player") or {}).get("avatar")]
    main_avatar = None
    if with_deck:
        counts: dict[str, int] = {}
        for m in with_deck:
            counts[m["player"]["avatar"]] = counts.get(m["player"]["avatar"], 0) + 1
        main_avatar = max(counts, key=counts.get)

    for m in matches:
        won = m.get("result") == "win"
        me, opp = m.get("player") or {}, m.get("opponent") or {}
        _bucket(by_avatar, me.get("avatar"), won)
        _bucket(by_elements, _elements(me.get("elements")), won)
        _bucket(vs_avatar, opp.get("avatar"), won)
        _bucket(vs_elements, _elements(opp.get("elements")), won)
        if m.get("on_play") is not None:
            _bucket(play, "going first" if m["on_play"] else "going second", won)
        _bucket(length, _length_bucket(m.get("match_time_minutes")), won)
        if main_avatar and me.get("avatar") == main_avatar:
            _bucket(main_vs, opp.get("avatar"), won)

    # Streaks and form (matches are newest first)
    results = [m.get("result") == "win" for m in matches]
    current = 0
    for r in results:
        if r != results[0]:
            break
        current += 1
    longest_loss = run = 0
    for r in results:
        run = 0 if r else run + 1
        longest_loss = max(longest_loss, run)
    recent = results[:20]
    earlier = results[20:]

    # Compare with everyone's ranked games in the latest Meta Report: a full two-week release
    # with minimum sample sizes, so a thin start of season can't show an Avatar at 100%.
    label, report = await _latest_report(site)
    ranked = (report or {}).get("ranked") or {}
    everyone = {r.get("avatar"): r.get("winRate") for r in ranked.get("archetypes") or []
                if isinstance(r, dict) and r.get("avatar") and not r.get("elements")}
    avatars_played = _table(by_avatar, "avatar", 1)
    for row in avatars_played:
        row["everyone_win_rate"] = everyone.get(row["avatar"])

    main_matchups = []
    if main_avatar:
        grid = ranked.get("matchups") or {}
        keys = [a.get("avatar") for a in grid.get("archetypes") or [] if isinstance(a, dict)]
        cells = grid.get("cells") or []
        everyone_vs: dict[str, Any] = {}
        if main_avatar in keys and keys.index(main_avatar) < len(cells):
            for other, cell in zip(keys, cells[keys.index(main_avatar)] or []):
                if isinstance(cell, dict) and cell.get("winRate") is not None:
                    everyone_vs[other] = cell["winRate"]
        main_matchups = _table(main_vs, "against")
        for row in main_matchups:
            row["everyone_with_this_avatar_win_rate"] = everyone_vs.get(row["against"])

    vs_avatar_rows = _table(vs_avatar, "against")
    by_rate = sorted(vs_avatar_rows, key=lambda r: r["win_rate"] or 0)
    vs_elements_rows = _table(vs_elements, "against_elements")
    by_rate_el = sorted(vs_elements_rows, key=lambda r: r["win_rate"] or 0)

    unreleased = sum(1 for m in matches if not m.get("deck_info_released", True))
    recent_games = [{
        "date": str(m.get("date") or "")[:10],
        "result": m.get("result"),
        "my_avatar": (m.get("player") or {}).get("avatar"),
        "my_elements": _elements((m.get("player") or {}).get("elements")),
        "opponent_avatar": (m.get("opponent") or {}).get("avatar"),
        "opponent_elements": _elements((m.get("opponent") or {}).get("elements")),
        "went_first": m.get("on_play"),
        "minutes": m.get("match_time_minutes"),
    } for m in matches[:15]]

    return safe({
        "found": True,
        "player": name,
        "period": period,
        "games_reviewed": len(matches),
        "record": {"wins": wins, "losses": len(matches) - wins, "win_rate": _pct(wins, len(matches))},
        "form": {
            "last_20_win_rate": _pct(sum(recent), len(recent)),
            "before_that_win_rate": _pct(sum(earlier), len(earlier)) if earlier else None,
            "current_streak": f"{current} {'win' if results[0] else 'loss'}{'' if current == 1 else ('s' if results[0] else 'es')}",
            "longest_losing_streak": longest_loss,
        },
        "main_avatar": main_avatar,
        "compared_with": (f"everyone's ranked games in the Meta Report for {label}" if label
                          else "no Meta Report published yet"),
        "avatars_played": avatars_played,
        "my_deck_elements": _table(by_elements, "elements", 1),
        "main_avatar_matchups": main_matchups,
        "toughest_opponent_avatars": by_rate[:5],
        "best_opponent_avatars": list(reversed(by_rate[-5:])) if len(by_rate) > 5 else [],
        "against_deck_elements": by_rate_el,
        "going_first_vs_second": _table(play, "turn_order", 1),
        "by_game_length": _table(length, "length", 1),
        "recent_games": recent_games,
        "notes": [n for n in [
            f"Groups need at least {REVIEW_MIN_GAMES} games to be listed; small samples swing a lot.",
            "everyone_win_rate numbers come from the latest Meta Report; blank means too few games there.",
            (f"{unreleased} of the newest games have no Avatar or elements yet: deck details appear after the "
             f"next Meta Report release (shown through {released_through})." if unreleased else None),
            "Deck lists are never shared for ranked games, so tips can't name specific cards from them. "
            "For card advice, run deck_check on the player's own list.",
        ] if n],
        "profile": profile,
    }, max_list=40)


# ----------------------------------------------------------------------
# Avatars
# ----------------------------------------------------------------------


async def avatar_stats(site: SiteClient, avatar: str | None = None, season: str = "current") -> dict:
    event = _season(season)
    if not avatar:
        rows = await site.get(site.path("avatars", event=event), ttl=SLOW_TTL)
        table = sorted(
            ({"avatar": r.get("name"), "games": r.get("total"), "wins": r.get("wins"), "losses": r.get("losses"),
              "win_rate": r.get("win_rate")} for r in rows or [] if isinstance(r, dict)),
            key=lambda r: -(r["games"] or 0),
        )
        return safe({"period": "this season" if event == "current" else "all time",
                     "avatars": table, "page": _link("/avatars")}, max_list=40)

    name = await _resolve_avatar(site, avatar)
    detail = await site.get(site.path("avatar", name, event=event), ttl=SLOW_TTL)
    matchups = await site.get(site.path("avatar", name, "matchups", event=event), ttl=SLOW_TTL)
    rows = [
        {"against": m.get("opponent"), "games": m.get("total"), "win_rate": m.get("win_rate")}
        for m in (matchups or {}).get("matchups") or [] if (m.get("total") or 0) >= 5
    ]
    rows.sort(key=lambda r: -(r["win_rate"] or 0))
    play, draw = detail.get("play_stats") or {}, detail.get("draw_stats") or {}
    return safe({
        "avatar": name,
        "period": "this season" if event == "current" else "all time",
        "games": detail.get("total_matches"),
        "win_rate": detail.get("win_rate"),
        "going_first_win_rate": play.get("win_rate"),
        "going_second_win_rate": draw.get("win_rate"),
        "best_matchups": rows[:6],
        "worst_matchups": list(reversed(rows[-6:])) if len(rows) > 6 else list(reversed(rows)),
        "note": "Matchups need at least 5 games to be listed.",
        "page": _link(f"/avatar/{name}"),
    })


# ----------------------------------------------------------------------
# Cards
# ----------------------------------------------------------------------


async def card_stats(site: SiteClient, card: str) -> dict:
    name = (card or "").strip()
    if not name:
        raise SiteError("Please name a card.")
    data = await site.get(site.path("card", name), allow_404=True)
    if not data or data.get("error"):
        return {"found": False, "message": f"No card called '{name}'."}
    keep = ("name", "type", "element", "cost", "rarity", "set", "text", "power", "defense", "threshold",
            "wins", "losses", "total_matches", "win_rate")
    out = {k: data.get(k) for k in keep if data.get(k) is not None}
    out["found"] = True
    out["note"] = "Win rate counts Summit ranked games where a deck ran the card."
    out["page"] = _link(f"/card/{data.get('name') or name}")
    return safe(out)


async def top_staples(site: SiteClient, element: str | None = None, card_type: str | None = None,
                      season: str | None = None, limit: int = 15) -> dict:
    # Only release-window snapshots: never from/through, which would ask PSO live.
    params: dict[str, Any] = {"limit": max(1, min(int(limit or 15), 40))}
    if element:
        params["element"] = element.strip().title()
    if card_type:
        params["type"] = card_type.strip().title()
    if season and season.strip().lower() in ("all", "all time", "lifetime"):
        params["season"] = "all"
    data = await site.get(site.path("staples", **params), ttl=SLOW_TTL)
    if not data or data.get("success") is False:
        raise SiteError((data or {}).get("error") or "Card data is unavailable right now.")
    return safe({k: v for k, v in data.items() if k not in ("terms_of_use",)}, max_list=40)


# ----------------------------------------------------------------------
# Meta report and trends
# ----------------------------------------------------------------------


async def meta_report(site: SiteClient, report: str | None = None) -> dict:
    listing = (await site.get(site.path("meta-reports"), ttl=SLOW_TTL)).get("reports") or []
    if not listing:
        return {"found": False, "message": "No Meta Report has been published yet."}
    slug = None
    if report:
        wanted = report.strip().lower()
        for r in listing:
            if wanted in (str(r.get("slug", "")).lower(), str(r.get("label", "")).lower()):
                slug = r["slug"]
                break
        if not slug:
            return {"found": False, "message": "No report by that name.",
                    "reports": [{"report": r.get("slug"), "covers": r.get("label")} for r in listing[:12]]}
    slug = slug or listing[0]["slug"]
    data = await site.get(site.path("meta-reports", slug), ttl=SLOW_TTL)
    body = {k: v for k, v in (data or {}).items() if k not in ("payload",)}
    if isinstance(body.get("ranked"), dict):
        # The deck-type grid is huge; deck_check reads it directly instead
        body["ranked"] = {k: v for k, v in body["ranked"].items() if k != "deckTypes"}
    return safe({
        "found": True,
        "report": slug,
        "page": _link(f"/meta-report/{slug}"),
        "other_reports": [r.get("slug") for r in listing[:6] if r.get("slug") != slug],
        **body,
    }, max_list=12)


async def meta_trends(site: SiteClient) -> dict:
    data = await site.get(site.path("deck-archetypes", "trends"), ttl=SLOW_TTL)
    info = {a.get("id"): a for a in (data or {}).get("archetypes") or [] if isinstance(a, dict)}

    def label(key: str) -> str:
        return (info.get(key) or {}).get("name") or key

    def elements_of(key: str) -> list[str]:
        raw = (info.get(key) or {}).get("elements") or key.replace("-", " ").title()
        return [e for e in ELEMENTS if e.lower() in str(raw).lower()]

    months, element_rows = [], []
    for m in (data or {}).get("months") or []:
        counts = {k: v for k, v in (m.get("counts") or {}).items() if isinstance(v, (int, float))}
        total = sum(counts.values())
        if not total:
            continue
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:8]
        months.append({
            "month": m.get("month"),
            "ranked_games": m.get("matches"),
            "top_archetypes": [{"archetype": label(k), "share_pct": _pct(v, total)} for k, v in top],
        })
        # Share of classified decks that play each element (a two-element deck counts for both)
        row = {"month": m.get("month")}
        for e in ELEMENTS:
            row[e] = _pct(sum(v for k, v in counts.items() if e in elements_of(k)), total)
        element_rows.append(row)
    return safe({
        "covers": {"from": data.get("start"), "through": data.get("through"), "next_release": data.get("nextRelease")},
        "element_share_by_month_pct": element_rows,
        "months": months,
        "note": ("Shares are of classified ranked decks per month; a two-element deck counts toward both "
                 "elements. Numbers update with each data release on the 1st and 15th."),
        "page": _link("/deck-archetypes"),
    }, max_list=14)


# ----------------------------------------------------------------------
# Top 8 events (the only tools that may link decks)
# ----------------------------------------------------------------------


def _top8_deck(deck: dict, place: int | None = None) -> dict:
    out = {"player": deck.get("player"), "avatar": deck.get("avatar"), "elements": deck.get("elements"),
           "deck_name": deck.get("deck_name")}
    if place:
        out["place"] = place
    if deck.get("deck_id"):
        out["deck_page"] = _link(f"/deck-rec/{deck['deck_id']}")
    return out


async def _top8_index(site: SiteClient) -> list[dict]:
    data = await site.get(site.path("top-8-events"), ttl=EVENT_TTL)
    return [e for e in (data or {}).get("events") or [] if isinstance(e, dict)]


async def top8_events(site: SiteClient, search: str | None = None, avatar: str | None = None,
                      event_format: str | None = None, limit: int = 10) -> dict:
    events = await _top8_index(site)
    if search:
        s = search.strip().lower()
        events = [e for e in events if s in str(e.get("name", "")).lower() or s in str(e.get("folder", "")).lower()]
    if avatar:
        a = avatar.strip().lower()
        events = [e for e in events if a in str(e.get("winner_avatar", "")).lower()]
    if event_format:
        f = event_format.strip().lower()
        events = [e for e in events if f in str(e.get("format", "")).lower()]
    events.sort(key=lambda e: str(e.get("event_date") or ""), reverse=True)
    limit = max(1, min(int(limit or 10), 25))
    return compact({
        "events": [{
            "event": e.get("folder"), "name": e.get("name"), "date": e.get("event_date"),
            "format": e.get("format"), "players": e.get("attendance") or e.get("player_count"),
            "winner": e.get("winner_username"), "winner_avatar": e.get("winner_avatar"),
            "page": _link(f"/top-8/{e.get('folder')}"),
        } for e in events[:limit]],
        "matching_events": len(events),
        "tip": "Use top8_event_decks with an event's 'event' value to see its decks.",
    })


async def top8_event_decks(site: SiteClient, event: str) -> dict:
    folder = (event or "").strip()
    if not folder:
        raise SiteError("Please name an event.")
    events = await _top8_index(site)
    match = next((e for e in events if str(e.get("folder", "")).lower() == folder.lower()), None)
    if match is None:
        close = [e for e in events if folder.lower() in str(e.get("name", "")).lower()
                 or folder.lower() in str(e.get("folder", "")).lower()]
        if len(close) != 1:
            return {"found": False, "message": f"No single Top 8 event matches '{folder}'.",
                    "matches": [e.get("folder") for e in close[:10]]}
        match = close[0]
    data = await site.get(site.path("events", match["folder"]), ttl=EVENT_TTL)
    top8 = data.get("top8_decks") or []
    cards = [{"card": c.get("name"), "in_pct_of_top8_decks": c.get("deck_percent"), "avg_copies": c.get("avg_played")}
             for c in (data.get("top8_card_data") or [])[:15]]
    return compact({
        "found": True,
        "event": data.get("event_name") or match.get("name"),
        "date": data.get("event_date_display") or match.get("event_date"),
        "format": data.get("format"),
        "players": match.get("attendance") or match.get("player_count"),
        "top_8": [_top8_deck(d, i + 1) for i, d in enumerate(top8[:8])],
        "most_played_cards_in_top_8": cards,
        "page": _link(f"/top-8/{match['folder']}"),
    })


async def top8_card_search(site: SiteClient, card: str) -> dict:
    name = (card or "").strip()
    if not name:
        raise SiteError("Please name a card.")
    data = await site.get(site.path("top-8-events", "card-search", card=name), ttl=EVENT_TTL)
    hits = (data or {}).get("matches") or {}
    by_folder = {e.get("folder"): e for e in await _top8_index(site)}
    rows = []
    for folder, positions in hits.items():
        info = by_folder.get(folder) or {}
        rows.append({"event": folder, "name": info.get("name"), "date": info.get("event_date"),
                     "decks_running_it": len(positions or []), "page": _link(f"/top-8/{folder}")})
    rows.sort(key=lambda r: str(r["date"] or ""), reverse=True)
    return compact({"card": data.get("card") or name, "events": rows, "events_count": len(rows)})


async def _recent_top8_decks_for_avatar(site: SiteClient, avatar: str, want: int = 5) -> list[dict]:
    """The newest Top 8 decks on an Avatar, reading at most 12 recent events."""
    events = sorted(await _top8_index(site), key=lambda e: str(e.get("event_date") or ""), reverse=True)
    found: list[dict] = []
    for e in events[:12]:
        if not e.get("has_top8"):
            continue
        try:
            data = await site.get(site.path("events", e["folder"]), ttl=EVENT_TTL)
        except SiteError:
            continue
        for place, deck in enumerate(data.get("top8_decks") or [], start=1):
            if str(deck.get("avatar", "")).lower() == avatar.lower():
                found.append({**_top8_deck(deck, place), "event": e.get("name"), "date": e.get("event_date")})
                if len(found) >= want:
                    return found
    return found


# ----------------------------------------------------------------------
# Archetype card patterns (tournament decks only)
# ----------------------------------------------------------------------


async def _tournament_archetypes(site: SiteClient) -> list[dict]:
    data = await site.get(site.path("deck-archetypes", source="tournament"), ttl=SLOW_TTL)
    return [g for g in (data or {}).get("groups") or [] if isinstance(g, dict)]


async def _archetype_patterns(site: SiteClient, group_id: str) -> dict:
    data = await site.get(site.path("deck-archetypes", group_id, source="tournament"), ttl=SLOW_TTL)
    return (data or {}).get("patterns") or {}


def _core_cards(patterns: dict, zone: str = "spellbook", limit: int = 12) -> list[dict]:
    rows = [r for r in patterns.get(zone) or [] if isinstance(r, dict)]
    rows.sort(key=lambda r: -(r.get("rate") or 0))
    return [{"card": r.get("name"), "in_pct_of_decks": round((r.get("rate") or 0) * 100), "avg_copies": r.get("avgCopies")}
            for r in rows[:limit]]


# ----------------------------------------------------------------------
# Matchup prep
# ----------------------------------------------------------------------


async def matchup_prep(site: SiteClient, my_avatar: str, opponent_avatar: str, season: str = "current") -> dict:
    mine = await _resolve_avatar(site, my_avatar)
    theirs = await _resolve_avatar(site, opponent_avatar)
    event = _season(season)
    result: dict[str, Any] = {"you": mine, "opponent": theirs,
                              "period": "this season" if event == "current" else "all time"}

    matchups = await site.get(site.path("avatar", mine, "matchups", event=event), ttl=SLOW_TTL)
    row = next((m for m in (matchups or {}).get("matchups") or []
                if str(m.get("opponent", "")).lower() == theirs.lower()), None)
    if row is None and event == "current":
        all_time = await site.get(site.path("avatar", mine, "matchups", event="all"), ttl=SLOW_TTL)
        row = next((m for m in (all_time or {}).get("matchups") or []
                    if str(m.get("opponent", "")).lower() == theirs.lower()), None)
        if row:
            result["period"] = "all time (not enough games this season)"
    result["head_to_head"] = (
        {"games": row.get("total"), "your_win_rate": row.get("win_rate")} if row
        else "No ranked games between these Avatars yet."
    )

    opponent_detail = await site.get(site.path("avatar", theirs, event=event), ttl=SLOW_TTL)
    result["opponent_overall"] = {
        "games": opponent_detail.get("total_matches"), "win_rate": opponent_detail.get("win_rate"),
        "going_first_win_rate": (opponent_detail.get("play_stats") or {}).get("win_rate"),
    }

    try:
        groups = [g for g in await _tournament_archetypes(site) if str(g.get("avatar", "")).lower() == theirs.lower()]
        groups.sort(key=lambda g: -(g.get("size") or 0))
        builds = []
        for g in groups[:2]:
            patterns = await _archetype_patterns(site, g["id"])
            builds.append({"build": g.get("name"), "tournament_decks": g.get("size"),
                           "cards_to_expect": _core_cards(patterns, limit=10)})
        result["what_they_usually_play"] = builds or "No tournament decks on this Avatar yet."
    except SiteError as exc:
        result["what_they_usually_play"] = str(exc)
    result["recent_top8_lists"] = await _recent_top8_decks_for_avatar(site, theirs, want=4)
    result["note"] = ("Win rates are Summit ranked games. Card lists come from public tournament "
                      "decks only, never from ranked decks.")
    return safe_top8(result)


def safe_top8(result: dict) -> dict:
    """Keep the Top 8 deck links in ``recent_top8_lists``; clean everything else."""
    lists = result.pop("recent_top8_lists", None)
    cleaned = safe(result)
    if lists is not None:
        cleaned["recent_top8_lists"] = compact(lists)
    return cleaned


# ----------------------------------------------------------------------
# Deck check
# ----------------------------------------------------------------------

_LINE = re.compile(r"^\s*(\d+)\s*x?\s+(.+?)\s*$", re.IGNORECASE)
_SECTION = re.compile(r"^\s*(avatar|spellbook|atlas|sites?|collection|sideboard|maybeboard)\b", re.IGNORECASE)


def parse_deck_text(text: str) -> dict:
    """'3 Fireball' style lines, with optional Avatar / Spellbook / Atlas headings."""
    deck: dict[str, list] = {"avatar": [], "spellbook": [], "atlas": [], "sideboard": []}
    section = "spellbook"
    for raw in (text or "").splitlines()[:300]:
        line = raw.strip()
        if not line:
            continue
        head = _SECTION.match(line)
        if head and not _LINE.match(line):
            word = head.group(1).lower()
            section = {"sites": "atlas", "site": "atlas", "collection": "sideboard",
                       "maybeboard": "sideboard"}.get(word, word)
            if ":" in line and line.split(":", 1)[1].strip() and section == "avatar":
                deck["avatar"].append({"name": line.split(":", 1)[1].strip(), "quantity": 1})
                section = "spellbook"  # 'Avatar: X' is one line; cards follow
            continue
        m = _LINE.match(line)
        if m:
            deck[section].append({"name": m.group(2), "quantity": int(m.group(1))})
        elif section == "avatar":
            deck["avatar"].append({"name": line, "quantity": 1})
            section = "spellbook"
    return deck


async def _card_elements(site: SiteClient) -> dict[str, dict]:
    cards = await site.get(site.path("deck-builder", "all-cards"), ttl=24 * 60 * 60)
    return {str(c.get("name", "")).lower(): c for c in cards or [] if isinstance(c, dict)}


def element_label(spellbook: list[dict]) -> str:
    """Top two elements by copies, alphabetical: the site's deck type rule."""
    totals = {e: 0 for e in ELEMENTS}
    for card in spellbook:
        qty = max(1, int(card.get("quantity") or 1))
        for part in str(card.get("elements") or "").split(","):
            part = part.strip()
            if part in totals:
                totals[part] += qty
    top = [e for e in sorted(ELEMENTS, key=lambda e: -totals[e]) if totals[e] > 0][:2]
    return " / ".join(sorted(top)) if top else "None"


async def deck_check(site: SiteClient, deck_url: str | None = None, deck_list: str | None = None) -> dict:
    """Compare a player's own deck to tournament decks of the same Avatar and elements.

    Nothing the player sends is stored. A Curiosa link is read through the
    site's Deck Builder (its own cache and rate limit).
    """
    if deck_url:
        url = deck_url.strip()
        if not re.match(r"^https?://", url) or not re.search(r"curiosa\.io|sorcerytcg\.com", url, re.IGNORECASE):
            raise SiteError("Please send a Curiosa deck link, or paste the list as text.")
        deck = await site.post(site.path("deck-builder", "fetch"), {"url": url}, ttl=SLOW_TTL)
        spellbook = deck.get("spellbook") or []
        atlas = deck.get("atlas") or []
        avatar = ((deck.get("avatar") or [{}])[0] or {}).get("name")
    elif deck_list:
        parsed = parse_deck_text(deck_list)
        lookup = await _card_elements(site)
        def enrich(cards):
            return [{**c, "elements": (lookup.get(c["name"].lower()) or {}).get("elements", "")} for c in cards]
        spellbook, atlas = enrich(parsed["spellbook"]), enrich(parsed["atlas"])
        avatar = (parsed["avatar"] or [{}])[0].get("name")
        unknown = [c["name"] for c in parsed["spellbook"] + parsed["atlas"] if c["name"].lower() not in lookup]
    else:
        raise SiteError("Send a Curiosa deck link or paste the deck list.")
    if not spellbook:
        raise SiteError("I couldn't find any Spellbook cards in that deck.")

    elements = element_label(spellbook)
    result: dict[str, Any] = {
        "avatar": avatar or "unknown (add an 'Avatar: <name>' line)",
        "deck_type": elements,
        "spellbook_cards": sum(int(c.get("quantity") or 1) for c in spellbook),
        "atlas_cards": sum(int(c.get("quantity") or 1) for c in atlas),
    }
    if deck_list and unknown:
        result["cards_not_recognised"] = unknown[:15]

    # Tournament archetype for this Avatar + elements
    try:
        groups = await _tournament_archetypes(site)
    except SiteError as exc:
        groups = []
        result["compared_with"] = str(exc)
    group = next((g for g in groups if avatar and str(g.get("avatar", "")).lower() == avatar.lower()
                  and g.get("elementsLabel") == elements), None)
    if group is None and avatar:
        same_avatar = sorted((g for g in groups if str(g.get("avatar", "")).lower() == avatar.lower()),
                             key=lambda g: -(g.get("size") or 0))
        group = same_avatar[0] if same_avatar else None
    if group:
        patterns = await _archetype_patterns(site, group["id"])
        mine = {str(c.get("name", "")).lower(): int(c.get("quantity") or 1) for c in spellbook}
        core = [r for r in patterns.get("spellbook") or [] if (r.get("rate") or 0) >= 0.6]
        popular = {str(r.get("name", "")).lower(): r for r in patterns.get("spellbook") or []}
        result["compared_with"] = {"archetype": group.get("name"), "tournament_decks": group.get("size"),
                                   "page": _link("/deck-archetypes")}
        result["common_cards_you_dont_run"] = [
            {"card": r.get("name"), "in_pct_of_decks": round((r.get("rate") or 0) * 100), "avg_copies": r.get("avgCopies")}
            for r in sorted(core, key=lambda r: -(r.get("rate") or 0)) if str(r.get("name", "")).lower() not in mine
        ][:10]
        def how_common(card):
            row = popular.get(str(card.get("name", "")).lower())
            return f"in {round(row['rate'] * 100)}% of these decks" if row and row.get("rate") else "rarely or never played here"
        result["your_unusual_cards"] = [
            {"card": c.get("name"), "copies": c.get("quantity"), "how_common": how_common(c)}
            for c in spellbook
            if ((popular.get(str(c.get("name", "")).lower()) or {}).get("rate") or 0) < 0.15
        ][:10]
    elif "compared_with" not in result:
        result["compared_with"] = "No tournament decks share this Avatar yet, so there's nothing to compare against."

    # How this deck type does in ranked, from the latest Meta Report
    try:
        result["deck_type_in_ranked"] = await _deck_type_matchups(site, elements, avatar)
    except SiteError as exc:
        result["deck_type_in_ranked"] = str(exc)

    # Card win rates for the deck's cards (saved site data)
    rates = []
    for c in spellbook[:40]:
        try:
            data = await site.get(site.path("card", c.get("name", "")), allow_404=True)
        except SiteError:
            continue
        if data and data.get("win_rate") is not None and (data.get("total_matches") or 0) >= 20:
            rates.append({"card": data.get("name"), "win_rate_when_in_deck": data.get("win_rate"),
                          "games": data.get("total_matches")})
    rates.sort(key=lambda r: r["win_rate_when_in_deck"])
    if rates:
        result["weakest_cards_by_ranked_win_rate"] = rates[:5]
        result["strongest_cards_by_ranked_win_rate"] = list(reversed(rates[-5:]))
    result["note"] = ("Your deck is not saved. Comparisons use public tournament decks and aggregate "
                      "Summit ranked numbers only.")
    return safe(result)


async def _deck_type_matchups(site: SiteClient, elements: str, avatar: str | None) -> Any:
    listing = (await site.get(site.path("meta-reports"), ttl=SLOW_TTL)).get("reports") or []
    if not listing:
        return "No Meta Report published yet."
    report = await site.get(site.path("meta-reports", listing[0]["slug"]), ttl=SLOW_TTL)
    deck_types = ((report or {}).get("ranked") or {}).get("deckTypes") or {}
    picks = deck_types.get("picks") or {}
    pick = (picks.get(f"{elements}|{avatar}") if avatar else None) or picks.get(f"{elements}|")
    if not pick:
        return f"Not enough {elements} games in the latest Meta Report ({listing[0].get('label')})."
    rows = pick.get("both") or pick.get("avatar") or []
    return {
        "report": listing[0].get("label"),
        "games": pick.get("games"),
        "win_rate": pick.get("winRate"),
        "hardest_matchups": [r for r in rows if (r.get("winRate") or 0) < 50][:5],
        "easiest_matchups": [r for r in reversed(rows) if (r.get("winRate") or 0) > 50][:5],
    }


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


async def store_products(site: SiteClient) -> dict:
    data = await site.get(site.path("store", "products"), ttl=5 * 60)
    items = []
    for p in (data or {}).get("products") or []:
        price = p.get("price_cents")
        items.append({
            "product": p.get("name"),
            "price": f"${price / 100:.2f}" if isinstance(price, int) else None,
            "in_stock": (p.get("stock_quantity") or 0) > 0,
            "description": p.get("description"),
            "line": p.get("product_line"),
        })
    return safe({"products": items, "buy_at": _link("/store"),
                 "shipping": "US only. Buying happens on the site."}, max_list=40, max_text=300)


# ----------------------------------------------------------------------
# Ranked recap
# ----------------------------------------------------------------------


def _drop_discord_ids(value: Any) -> Any:
    """The recap keeps Discord user IDs next to names; AI apps only need the names."""
    if isinstance(value, dict):
        return {k: _drop_discord_ids(v) for k, v in value.items()
                if k != "names" and not str(k).endswith("_id") and str(k) != "id"}
    if isinstance(value, list):
        return [_drop_discord_ids(v) for v in value
                if not (isinstance(v, int) and not isinstance(v, bool) and v > 10**15)
                and not (isinstance(v, str) and v.isdigit() and len(v) >= 16)]
    return value


async def ranked_recap(site: SiteClient, kind: str = "daily", day: str | None = None) -> dict:
    kind = "weekly" if (kind or "").strip().lower().startswith("week") else "daily"
    if day:
        try:
            wanted = date.fromisoformat(day.strip())
        except ValueError:
            raise SiteError("Give the date as YYYY-MM-DD.")
        tries = [wanted]
    else:
        today = datetime.now(timezone.utc).date()
        tries = [today - timedelta(days=n) for n in range(1, 4 if kind == "daily" else 8)]
    for d in tries:
        data = await site.get(site.path("match-history", "recap", kind=kind, date=d.isoformat()), allow_404=True)
        if data:
            return safe({"recap": kind, "date": d.isoformat(), **_drop_discord_ids(data),
                         "page": _link(f"/match-history?recap={kind}&date={d.isoformat()}")})
    return {"found": False, "message": f"No {kind} recap saved for that date."}


# ----------------------------------------------------------------------
# Signed-in player's own data (the /mcp/account connector)
# ----------------------------------------------------------------------

CARD_MIN_GAMES = 8  # a card needs this many games played to be called out


async def my_account(site: SiteClient, user_token: str) -> dict:
    me = await site.get(site.path("mcp", "me"), ttl=60, user_token=user_token)
    return {"signed_in_as": me.get("name"), "profile": _link(me.get("profile") or "/"),
            "connected_app": me.get("app")}


def _card_highlights(stats: dict) -> dict:
    cards = [c for c in stats.get("cards") or [] if (c.get("games") or 0) >= CARD_MIN_GAMES]
    with_effect = [c for c in cards if c.get("effect") is not None]
    with_effect.sort(key=lambda c: c["effect"])

    def row(c):
        return {"card": c["name"], "element": c.get("element"), "games_played_in": c["games"],
                "win_rate_when_played": c["win_rate"], "win_rate_when_not_played": c.get("win_rate_not_played"),
                "effect_points": c["effect"]}

    return {
        "games_with_card_data": stats.get("games"),
        "win_rate": stats.get("win_rate"),
        "most_played": [row(c) for c in cards[:10]],
        "lifts_you_most": [row(c) for c in reversed(with_effect[-6:])],
        "drags_you_down": [row(c) for c in with_effect[:6] if c["effect"] < 0],
        "how_to_read": (f"Cards played in at least {CARD_MIN_GAMES} games. effect_points = win rate in games "
                        "where the card was played minus games where it wasn't. A negative number can also "
                        "mean the card shows up in games that were already going badly, so treat it as a "
                        "question to look at, not a verdict."),
    }


async def my_card_stats(site: SiteClient, user_token: str, season: str = "all") -> dict:
    event = "current" if _season(season) == "current" else "lifetime"
    stats = await site.get(site.path("mcp", "me", "card-stats", event=event, queue="ranked"),
                           user_token=user_token)
    return safe({"period": "this season" if event == "current" else "all seasons",
                 "queue": "ranked", **_card_highlights(stats)}, max_list=12)


async def my_match_review(site: SiteClient, user_token: str, season: str = "all") -> dict:
    """The signed-in player's own review: every game's avatars (no release hold-back) plus Card Stats."""
    me = await site.get(site.path("mcp", "me"), ttl=60, user_token=user_token)
    event = _season(season)
    matches, released_through = await _collect_matches(
        site, lambda page: site.path("mcp", "me", "matches", season=event, page=page, per_page=100),
        user_token=user_token)
    result = await _review(site, matches, me.get("name") or "you", event, released_through,
                           _link(me.get("profile") or "/"))
    if result.get("found") and result.get("games_reviewed"):
        try:
            stats = await site.get(site.path("mcp", "me", "card-stats",
                                             event="current" if event == "current" else "lifetime", queue="ranked"),
                                   user_token=user_token)
            result["card_stats"] = compact(_card_highlights(stats), max_list=8)
        except SiteError as exc:
            if isinstance(exc, SignInExpired):
                raise
            result["card_stats"] = "Card Stats are unavailable right now."
        result["notes"] = [n for n in result.get("notes") or [] if "Meta Report release" not in n] + [
            "Signed in: this includes your newest games, and Card Stats come from your own played cards "
            "(private on your profile unless you shared them)."]
    result["signed_in"] = True
    return result


async def my_decks(site: SiteClient, user_token: str, season: str = "all") -> dict:
    """The signed-in player's OWN ranked deck lists with results (Bruce, 2026-11-28).

    The only tool allowed to return ranked deck lists, so it skips ``safe``:
    the site only ever answers with the token owner's own decks, never an
    opponent's, and this tool never mixes in anyone else's data.
    """
    event = _season(season)
    data = await site.get(site.path("mcp", "me", "decks", season=event), user_token=user_token)
    decks = []
    for d in (data or {}).get("decks") or []:
        if not isinstance(d, dict):
            continue
        decks.append({
            "avatar": d.get("avatar"),
            "elements": _elements(d.get("elements")),
            "games": d.get("games"), "wins": d.get("wins"), "losses": d.get("losses"),
            "win_rate": d.get("win_rate"),
            "first_played": str(d.get("first_played") or "")[:10],
            "last_played": str(d.get("last_played") or "")[:10],
            "results_against": (d.get("against") or [])[:8],
            "cards": d.get("cards") or {},
        })
    return {
        "period": "this season" if event == "current" else "recent ranked games",
        "decks": decks[:10],
        "note": ("These are the signed-in player's own ranked decks, newest first, grouped by exact list. "
                 "Only share them with this player."),
    }
