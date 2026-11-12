"""Every automatically run ladder and bracket on one page.

The site has grown a lot of separate places to check: the season ladder and
its ticket-holder top cut, the underdog avatar bracket, the Limited ladder,
site brackets (official and community), and the precon ladder. `/standings`
brings them together: one card per system with what it is, where it is at
and a link, and, for a logged-in player, where they stand in each one. The
Community Series stays on its own page (Bruce, 2026-11-11).

Everything here is read from our own databases. Nothing calls Play Sorcery
Online or any other outside service per visitor.
"""

import logging
import threading
import time

import webapp_config
from repositories.brackets import BracketRepository
from services.brackets import BracketService, is_community
from services.leaderboard import LeaderboardService, unique_players, voice_requirement
from services.ticket_holders import ensure_roster_fresh, ticket_holder_ids
from services.ticket_leaderboard import TICKET_HOLDERS_SHOWN

logger = logging.getLogger(__name__)

# The season top cut takes this many ticket holders (the Discord channel's 32).
TOP_CUT_SIZE = TICKET_HOLDERS_SHOWN
TOP_SHOWN = 3
# The public part of the page is the same for everyone, so it is built at
# most once a minute however many people open it.
CACHE_SECONDS = 60
# Mirrors the bot's underdog standings card: Bruce's Season 8 call.
DEFAULT_UNDERDOG_LEFT_OUT = {"season 8": ("Frostmage", "Lavamancer")}


def underdog_left_out(event_name) -> list[str]:
    table = getattr(webapp_config, "UNDERDOG_LEFT_OUT", DEFAULT_UNDERDOG_LEFT_OUT)
    wanted = str(event_name or "").strip().lower()
    for name, avatars in table.items():
        if str(name).strip().lower() == wanted:
            return list(avatars)
    return []


def _games(entry) -> int:
    return (entry.get("wins") or 0) + (entry.get("losses") or 0)


class StandingsHubService:
    def __init__(self, leaderboard=None, bracket_repo=None, bracket_service=None):
        self._leaderboard = leaderboard or LeaderboardService()
        self._bracket_repo = bracket_repo or BracketRepository()
        self._brackets = bracket_service or BracketService()
        self._cache = None
        self._cache_at = 0.0
        self._lock = threading.Lock()

    # -- Entry point ----------------------------------------------

    def get_hub(self, viewer_id: str | None = None) -> dict:
        state = self._state()
        systems = [dict(s) for s in state["systems"]]
        if viewer_id:
            viewer_id = str(viewer_id)
            for system in systems:
                try:
                    system["you"] = self._viewer(system["key"], state, viewer_id)
                except Exception as e:
                    logger.warning("Standings hub: %s viewer block failed: %s", system["key"], e)
                    system["you"] = None
        return {
            "systems": systems,
            "logged_in": bool(viewer_id),
            "built_at": state["built_at"],
        }

    def _state(self) -> dict:
        with self._lock:
            if self._cache and time.time() - self._cache_at < CACHE_SECONDS:
                return self._cache
            state = self._build()
            self._cache, self._cache_at = state, time.time()
            return state

    def _build(self) -> dict:
        state = {"systems": [], "built_at": int(time.time()), "private": {}}
        for key, builder in (
            ("season", self._season),
            ("underdog", self._underdog),
            ("limited", self._limited),
            ("precon", self._precon),
            ("brackets", self._bracket_list),
        ):
            try:
                system, private = builder()
            except Exception as e:
                logger.error("Standings hub: %s failed: %s", key, e, exc_info=True)
                continue
            if system:
                state["systems"].append({"key": key, **system})
                state["private"][key] = private
        return state

    # -- Season ladder + ticket-holder top cut --------------------

    def _season(self):
        data = self._leaderboard.get_event_leaderboard()
        event = data.get("event")
        standings = unique_players(data.get("leaderboard") or [])
        ensure_roster_fresh(self._bracket_repo)
        holders = ticket_holder_ids(self._bracket_repo)

        players = []
        for overall, entry in enumerate(standings, 1):
            players.append({
                "user_id": str(entry["id"]),
                "display_name": entry.get("name"),
                "elo": entry.get("event_elo"),
                "games": _games(entry),
                "voice_games": entry.get("voice_games", 0),
                "avatar": entry.get("avatar"),
                "overall_rank": overall,
                "is_ticket_holder": str(entry["id"]) in holders,
            })
        ticketed = [p for p in players if p["is_ticket_holder"]] if holders else []
        for rank, p in enumerate(ticketed, 1):
            p["ticket_rank"] = rank
        cut_line = ticketed[TOP_CUT_SIZE - 1]["elo"] if len(ticketed) >= TOP_CUT_SIZE else None

        system = {
            "title": (event or {}).get("event_name") or "Season ladder",
            "group": "Ladders",
            "kind": "ladder",
            "status": "live" if event else "between_seasons",
            "blurb": (
                f"Ranked online games. The top {TOP_CUT_SIZE} ticket holders on the ladder "
                "(Patreon supporters count) qualify for the Post Season Bracket."
            ),
            "link": "/elo",
            "links": [{"to": "/brackets", "label": "Season Top Cut"}],
            "ends_at": (event or {}).get("end_date"),
            "facts": [
                {"label": "Players", "value": len(players)},
                {"label": "Ticket holders playing", "value": len(ticketed)},
                {"label": f"#{TOP_CUT_SIZE} cut line", "value": round(cut_line) if cut_line is not None else "Open"},
            ],
            "top": [
                {"rank": p["overall_rank"], "name": p["display_name"], "value": round(p["elo"] or 0), "unit": "ELO"}
                for p in players[:TOP_SHOWN]
            ],
        }
        private = {
            "by_id": {p["user_id"]: p for p in players},
            "cut_line": cut_line,
            "ticketed": len(ticketed),
            "has_roster": bool(holders),
            "event": event,
        }
        return system, private

    # -- Underdog avatar bracket ----------------------------------

    def _underdog(self):
        from services.underdog_bracket import underdog_field

        event = self._leaderboard._elo_repo.get_active_event()
        if not event:
            return None, None  # Only a race while a season is running
        left_out = underdog_left_out(event.get("event_name"))
        field = underdog_field(event.get("event_id"), exclude=left_out)
        names = self._brackets._site_names([p["user_id"] for p in field["players"]])
        players = [
            {**p, "display_name": names.get(str(p["user_id"])) or p["display_name"]}
            for p in field["players"]
        ]
        system = {
            "title": "Underdog Bracket",
            "group": "Ladders",
            "kind": "race",
            "status": "live",
            "blurb": (
                "The best player on each of the season's 8 weakest avatars "
                f"(at least {field['min_games']} games on it) plays an end-of-season bracket."
                + (f" Left out this season: {', '.join(left_out)}." if left_out else "")
            ),
            "link": "/avatars",
            "links": [{"to": "/brackets?format=underdog", "label": "Underdog brackets"}],
            "ends_at": event.get("end_date"),
            "facts": [{"label": "Field so far", "value": f"{len(players)} of 8"}],
            "top": [
                {"rank": i, "name": p["display_name"], "value": p["avatar"], "unit": None}
                for i, p in enumerate(players, 1)
            ],
        }
        private = {"by_id": {str(p["user_id"]): (i, p) for i, p in enumerate(players, 1)}}
        return system, private

    # -- Limited ladder --------------------------------------------

    def _limited(self):
        from repositories import limited_repo
        from services.pilots import is_pilot_active

        if not is_pilot_active("limited_leaderboard"):
            return None, None
        ladder = limited_repo.get_limited_season_ladder()
        players = ladder.get("players") or []
        names = self._brackets._site_names([p["user_id"] for p in players])
        for rank, p in enumerate(players, 1):
            p["rank"] = rank
            p["display_name"] = names.get(str(p["user_id"])) or p["display_name"]
        system = {
            "title": ladder.get("event_name") or "Limited ladder",
            "group": "Ladders",
            "kind": "ladder",
            "status": "live" if limited_repo.get_active_limited_event() else "finished",
            "blurb": "Limited runs reported through the Summit. The season's best play the Limited bracket.",
            "link": "/elo?board=limited",
            "links": [{"to": "/brackets?format=limited", "label": "Limited brackets"}],
            "ends_at": None,
            "facts": [{"label": "Players", "value": len(players)}],
            "top": [
                {"rank": p["rank"], "name": p["display_name"], "value": round(p["elo"] or 0), "unit": "ELO"}
                for p in players[:TOP_SHOWN]
            ],
        }
        return system, {"by_id": {str(p["user_id"]): p for p in players}}

    # -- Precon ladder (Lavamancer vs Frostmage) ------------------

    def _precon(self):
        """The precon ladder's card.

        The ladder is built in its own branch. Until it is in, or before its
        first season starts, this is a "coming soon" card;
        ``services.precon_hub.hub_summary()`` returns ``{"system": {...},
        "players": [{user_id, display_name, rating, rank, games,
        provisional}]}`` (best first) once there is a ladder to show.
        """
        try:
            from services import precon_hub
        except ImportError:
            precon_hub = None
        summary = None
        if precon_hub and hasattr(precon_hub, "hub_summary"):
            summary = precon_hub.hub_summary()
        if not summary:
            return {
                "title": "Precon Ladder: Lavamancer vs Frostmage",
                "group": "Ladders",
                "kind": "ladder",
                "status": "coming_soon",
                "blurb": (
                    "A 4-week ladder for the two precons, rated with Glicko-2. "
                    "Queue with Lavamancer (LM) or Frostmage (FM)."
                ),
                "link": None,
                "links": [],
                "ends_at": None,
                "facts": [],
                "top": [],
            }, {"by_id": {}}
        players = summary.get("players") or []
        system = {"group": "Ladders", "kind": "ladder", "links": [], "facts": [], "top": [], **summary["system"]}
        if not system["top"]:
            system["top"] = [
                {"rank": p["rank"], "name": p["display_name"], "value": round(p["rating"] or 0), "unit": "rating"}
                for p in players[:TOP_SHOWN]
            ]
        return system, {"by_id": {str(p["user_id"]): p for p in players}}

    # -- Site brackets ---------------------------------------------

    def _bracket_list(self):
        brackets = self._brackets.list_brackets()
        live = [b for b in brackets if b["status"] == "published"]
        finished = [b for b in brackets if b["status"] == "complete"]

        def row(b):
            champ = b.get("champion") or {}
            return {
                "slug": b["slug"],
                "name": b["name"],
                "format": b.get("format") or "constructed",
                "community": is_community(b),
                "organizer": b.get("organizer_name"),
                "entrants": b.get("entrant_count"),
                "open_matches": b.get("open_matches", 0),
                "champion": champ.get("name") or champ.get("display_name"),
                "status": b["status"],
            }

        system = {
            "title": "Brackets",
            "group": "Brackets",
            "kind": "brackets",
            "status": "live" if live else ("finished" if finished else "none"),
            "blurb": "Season top cuts, Limited and Underdog brackets, and community brackets run on the site.",
            "link": "/brackets",
            "links": [],
            "ends_at": None,
            "facts": [
                {"label": "Being played", "value": len(live)},
                {"label": "Finished", "value": len(finished)},
            ],
            "top": [],
            "live": [row(b) for b in live],
            "recent": [row(b) for b in finished[:3]],
        }
        return system, {"live": live}

    # -- The viewer's own place in each ----------------------------

    def _viewer(self, key: str, state: dict, viewer_id: str) -> dict | None:
        private = state["private"].get(key) or {}
        if key == "season":
            return self._you_season(private, viewer_id)
        if key == "underdog":
            hit = private["by_id"].get(viewer_id)
            if not hit:
                return {"state": "out", "headline": "Not in the field right now",
                        "detail": "Be the best player on one of the 8 weakest avatars to take its spot."}
            seed, p = hit
            return {"state": "in", "headline": f"In the field on {p['avatar']}",
                    "detail": f"Seed {seed} of 8 · {p['wins']}-{p['losses']} on {p['avatar']}"}
        if key in ("limited", "precon"):
            p = private.get("by_id", {}).get(viewer_id)
            if not p:
                return {"state": "none", "headline": "No games yet", "detail": None}
            rating = p.get("elo", p.get("rating"))
            detail = f"{round(rating or 0)} rating · {_games(p) if 'wins' in p else p.get('games', 0)} games"
            if p.get("provisional"):
                detail += " · provisional"
            return {"state": "ranked", "headline": f"Rank #{p['rank']}", "detail": detail}
        if key == "brackets":
            return self._you_brackets(private, viewer_id)
        return None

    def _you_season(self, private, viewer_id):
        p = private["by_id"].get(viewer_id)
        voice = voice_requirement()
        if not p:
            return {"state": "none", "headline": "No ranked games this season",
                    "detail": "Queue in the Summit Discord to get on the ladder."}
        rank = f"#{p['overall_rank']} on the ladder · {round(p['elo'] or 0)} ELO · {p['games']} games"
        notes = []
        if voice.get("enforced") and p["voice_games"] < voice["min_games"]:
            notes.append(f"{p['voice_games']} of {voice['min_games']} voice games for the top cut")
        if private["has_roster"] and not p["is_ticket_holder"]:
            return {"state": "no_ticket", "headline": "Not qualified for the Post Season Bracket",
                    "detail": rank + ". It takes a season ticket or Patreon.", "notes": notes,
                    "action": {"to": "/store", "label": "Get a ticket"}}
        ticket_rank = p.get("ticket_rank")
        if ticket_rank and ticket_rank <= TOP_CUT_SIZE:
            return {"state": "in", "headline": f"Qualified for the Post Season Bracket · #{ticket_rank} of {TOP_CUT_SIZE}",
                    "detail": rank, "notes": notes}
        gap = None
        if private["cut_line"] is not None and p["elo"] is not None:
            gap = round(private["cut_line"] - p["elo"])
        headline = (
            f"Not qualified yet · #{ticket_rank} of the ticket holders" if ticket_rank else "On the ladder"
        )
        if gap is not None and gap > 0:
            notes.insert(0, f"{gap} ELO behind #{TOP_CUT_SIZE}")
        return {"state": "out", "headline": headline, "detail": rank, "notes": notes}

    def _you_brackets(self, private, viewer_id):
        mine = []
        for b in private.get("live", []):
            entrants = self._bracket_repo.get_entrants(b["bracket_id"])
            entrant = next((e for e in entrants if str(e.get("user_id") or "") == viewer_id), None)
            if not entrant:
                continue
            placement = self._brackets.placements(b["bracket_id"]).get(entrant["seed"])
            mine.append({
                "slug": b["slug"], "name": b["name"], "seed": entrant["seed"],
                "alive": placement is None,
                "label": "Still in" if placement is None else (
                    self._brackets.finish_label(placement, b.get("format")) or "Out"),
            })
        todo = []
        for m in self._brackets.get_player_open_matches(viewer_id):
            opp = m["p2_name"] if str(m.get("p1_user_id")) == viewer_id else m["p1_name"]
            todo.append({
                "slug": m["slug"], "bracket_name": m["bracket_name"],
                "round_title": m.get("round_title"), "opponent": opp, "needs": m["needs"],
            })
        if not mine and not todo:
            return {"state": "none", "headline": "Not in a bracket being played", "detail": None}
        alive = [b for b in mine if b["alive"]]
        return {
            "state": "in" if alive else "out",
            "headline": (
                f"Still in {len(alive)} bracket{'s' if len(alive) != 1 else ''}" if alive
                else "Out of every bracket being played"
            ),
            "detail": None,
            "brackets": mine,
            "todo": todo,
        }


_service = None


def get_service() -> StandingsHubService:
    global _service
    if _service is None:
        _service = StandingsHubService()
    return _service
