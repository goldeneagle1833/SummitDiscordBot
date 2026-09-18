"""Bracket orchestration: seeding, publishing, and player-reported results.

Drafts are admin-only. Publishing freezes the field into a match tree, after
which the two players in a match settle it between them: one reports, the
other confirms, and the winner moves on. The confirmation window mirrors the
site's existing 48-hour match confirmation flow.
"""

import logging
import random
import re
import time
from datetime import datetime

from repositories.brackets import BracketRepository
from services.bracket_builder import (
    advance_winner,
    bracket_size_for,
    build_matches,
    champion,
    winner_name,
)
from services.leaderboard import LeaderboardService
from services.ticket_holders import ticket_holder_ids

logger = logging.getLogger(__name__)

SEED_SOURCES = ("ticket_holders", "overall", "manual")


class BracketError(Exception):
    """A bracket action that cannot be carried out."""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "bracket"


class BracketService:
    def __init__(self, repo=None, leaderboard_service=None):
        self._repo = repo or BracketRepository()
        self._leaderboard_override = leaderboard_service

    @property
    def _leaderboard(self):
        """Built on demand so database paths resolve at call time."""
        return self._leaderboard_override or LeaderboardService()

    # -- Seed pool ------------------------------------------------

    def get_seed_pool(self, source: str = "ticket_holders") -> dict:
        """Ladder standings to seed from, flagged with ticket-holder status.

        Mirrors the bot's leaderboard message: current-event ELO, restricted to
        players who actually played this event, best first.
        """
        data = self._leaderboard.get_event_leaderboard()
        standings = data.get("leaderboard") or []
        elo_key = "event_elo"

        if not standings:
            # Same fallback the bot uses: with no event running, rank on
            # lifetime ELO instead of leaving the pool empty.
            standings = self._leaderboard.get_leaderboard()
            elo_key = "elo"

        holders = ticket_holder_ids(self._repo)

        players = []
        for entry in standings:
            user_id = str(entry["id"])
            is_holder = user_id in holders
            if source == "ticket_holders" and holders and not is_holder:
                continue
            players.append(
                {
                    "user_id": user_id,
                    "display_name": entry["name"],
                    "elo": entry.get(elo_key),
                    "games": (entry.get("wins") or 0) + (entry.get("losses") or 0),
                    "is_ticket_holder": is_holder,
                }
            )

        return {
            "event": data.get("event"),
            "players": players,
            "ticket_roster_size": len(holders),
            # Without a synced roster we cannot filter, so say so rather than
            # silently seeding a bracket from the wrong pool.
            "ticket_filter_applied": bool(holders) and source == "ticket_holders",
        }

    # -- Draft management -----------------------------------------

    def create_bracket(
        self,
        name: str,
        size: int,
        source: str = "ticket_holders",
        created_by: str | None = None,
        confirm_hours: int = 48,
    ) -> dict:
        """Create a draft bracket seeded with the top `size` players."""
        name = (name or "").strip()
        if not name:
            raise BracketError("A bracket needs a name")
        if source not in SEED_SOURCES:
            raise BracketError(f"Unknown seed source '{source}'")
        try:
            size = int(size)
        except (TypeError, ValueError):
            raise BracketError("Size must be a number") from None
        if size < 2 or size > 256:
            raise BracketError("Size must be between 2 and 256")

        pool = self.get_seed_pool(source) if source != "manual" else {"players": [], "event": None}
        entrants = pool["players"][:size]

        slug = self._unique_slug(slugify(name))
        bracket_id = self._repo.create_bracket(
            {
                "slug": slug,
                "name": name,
                "entrant_count": len(entrants),
                "bracket_size": bracket_size_for(max(len(entrants), 2)),
                "seeded_from": source,
                "elo_event_name": (pool.get("event") or {}).get("event_name"),
                "confirm_hours": confirm_hours,
                "created_by": created_by,
            }
        )
        if entrants:
            self._repo.replace_entrants(bracket_id, entrants)

        return {
            "bracket_id": bracket_id,
            "slug": slug,
            "entrant_count": len(entrants),
            "requested_size": size,
            "short_by": max(0, size - len(entrants)),
            "ticket_filter_applied": pool.get("ticket_filter_applied", False),
        }

    def _unique_slug(self, base: str) -> str:
        slug = base
        suffix = 2
        while self._repo.get_bracket(slug=slug):
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    def set_entrants(self, bracket_id: int, entrants: list[dict]) -> dict:
        """Replace the seeded field. Order in the list is the seeding order."""
        bracket = self._require_draft(bracket_id)

        cleaned = []
        seen = set()
        for entrant in entrants or []:
            display_name = (entrant.get("display_name") or "").strip()
            if not display_name:
                continue
            user_id = entrant.get("user_id")
            user_id = str(user_id) if user_id else None
            # The same account cannot occupy two seeds.
            if user_id and user_id in seen:
                continue
            if user_id:
                seen.add(user_id)
            cleaned.append(
                {
                    "user_id": user_id,
                    "display_name": display_name,
                    "elo": entrant.get("elo"),
                    "games": entrant.get("games"),
                    "is_ticket_holder": entrant.get("is_ticket_holder"),
                }
            )

        self._repo.replace_entrants(bracket_id, cleaned)
        self._repo.set_counts(
            bracket["bracket_id"],
            len(cleaned),
            bracket_size_for(len(cleaned)) if len(cleaned) >= 2 else 0,
        )
        return {"entrant_count": len(cleaned)}

    def shuffle_seeds(self, bracket_id: int) -> dict:
        """Randomise the seeding order of the current field."""
        self._require_draft(bracket_id)
        entrants = self._repo.get_entrants(bracket_id)
        random.shuffle(entrants)
        return self.set_entrants(bracket_id, entrants)

    def move_entrant(self, bracket_id: int, seed: int, to_seed: int) -> dict:
        """Move one entrant to a different seed, shifting the rest along."""
        self._require_draft(bracket_id)
        entrants = self._repo.get_entrants(bracket_id)
        if not 1 <= seed <= len(entrants) or not 1 <= to_seed <= len(entrants):
            raise BracketError("Seed out of range")
        entrant = entrants.pop(seed - 1)
        entrants.insert(to_seed - 1, entrant)
        return self.set_entrants(bracket_id, entrants)

    def publish(self, bracket_id: int) -> dict:
        """Freeze the field into a match tree and make the bracket public."""
        bracket = self._require_draft(bracket_id)
        entrants = self._repo.get_entrants(bracket_id)
        if len(entrants) < 2:
            raise BracketError("A bracket needs at least 2 entrants before publishing")

        matches = build_matches(entrants)
        self._repo.replace_matches(bracket_id, matches)
        self._repo.set_counts(bracket_id, len(entrants), bracket_size_for(len(entrants)))
        self._repo.set_status(bracket_id, "published")

        return {
            "slug": bracket["slug"],
            "entrant_count": len(entrants),
            "bracket_size": bracket_size_for(len(entrants)),
            "matches": len([m for m in matches if m["state"] != "empty"]),
            "byes": len([m for m in matches if m["state"] == "bye"]),
        }

    def unpublish(self, bracket_id: int) -> bool:
        """Send a bracket back to draft, discarding its match tree."""
        bracket = self._repo.get_bracket(bracket_id=bracket_id)
        if not bracket:
            raise BracketError("Bracket not found")
        self._repo.replace_matches(bracket_id, [])
        return self._repo.set_status(bracket_id, "draft")

    def _require_draft(self, bracket_id: int) -> dict:
        bracket = self._repo.get_bracket(bracket_id=bracket_id)
        if not bracket:
            raise BracketError("Bracket not found")
        if bracket["status"] != "draft":
            raise BracketError("Seeding can only be changed while the bracket is a draft")
        return bracket

    # -- Reads ----------------------------------------------------

    def get_bracket_by_slug(self, slug: str) -> dict | None:
        return self._repo.get_bracket(slug=slug)

    def update_bracket(self, bracket_id: int, fields: dict) -> bool:
        return self._repo.update_bracket(bracket_id, fields)

    def delete_bracket(self, bracket_id: int) -> bool:
        return self._repo.delete_bracket(bracket_id)

    def list_brackets(self, include_drafts: bool = False) -> list[dict]:
        brackets = self._repo.list_brackets(published_only=not include_drafts)
        for bracket in brackets:
            matches = self._repo.get_matches(bracket["bracket_id"])
            bracket["champion"] = champion(matches) if matches else None
            bracket["open_matches"] = len(
                [m for m in matches if m["state"] == "pending" and _is_playable(m)]
            )
        return brackets

    def get_bracket_detail(self, slug: str, include_drafts: bool = False) -> dict | None:
        bracket = self._repo.get_bracket(slug=slug)
        if not bracket:
            return None
        if bracket["status"] == "draft" and not include_drafts:
            return None

        self.auto_confirm_expired()
        bracket = self._repo.get_bracket(slug=slug)

        matches = self._repo.get_matches(bracket["bracket_id"])
        rounds = {}
        for match in matches:
            if match["state"] == "empty":
                continue
            bucket = rounds.setdefault(
                match["round"],
                {"round": match["round"], "title": match["round_title"], "matches": []},
            )
            bucket["matches"].append({**match, "playable": _is_playable(match)})

        return {
            "bracket": bracket,
            "entrants": self._repo.get_entrants(bracket["bracket_id"]),
            "rounds": [rounds[key] for key in sorted(rounds)],
            "champion": champion(matches) if matches else None,
        }

    def get_player_open_matches(self, user_id: str) -> list[dict]:
        """Matches where this player still owes a report or a confirmation."""
        rows = self._repo.get_player_matches(str(user_id))
        open_matches = []
        for row in rows:
            if not _is_playable(row):
                continue
            needs = None
            if row["state"] == "pending":
                needs = "report"
            elif row["state"] == "reported" and row["reported_by"] != str(user_id):
                needs = "confirm"
            if needs:
                open_matches.append({**row, "needs": needs})
        return open_matches

    # -- Results --------------------------------------------------

    def report_result(self, slug: str, match_no: int, user_id: str, winner_user_id: str) -> dict:
        """One player reports the result; the opponent has to confirm it."""
        bracket, match = self._require_live_match(slug, match_no)
        user_id = str(user_id)
        winner_user_id = str(winner_user_id)

        if user_id not in (match["p1_user_id"], match["p2_user_id"]):
            raise BracketError("Only the two players in this match can report it")
        if match["state"] != "pending":
            raise BracketError("This match has already been reported")
        if winner_user_id not in (match["p1_user_id"], match["p2_user_id"]):
            raise BracketError("The winner has to be one of the two players")

        window = int(bracket["confirm_hours"] or 48) * 3600
        self._repo.update_match(
            bracket["bracket_id"],
            match_no,
            {
                "state": "reported",
                "reported_by": user_id,
                "reported_winner_id": winner_user_id,
                "reported_at": datetime.now().isoformat(),
                "expires_at": int(time.time()) + window,
            },
        )
        return {
            "state": "reported",
            "awaiting": self._opponent(match, user_id),
            "expires_in_hours": bracket["confirm_hours"],
        }

    def confirm_result(self, slug: str, match_no: int, user_id: str, agree: bool = True) -> dict:
        """The opponent confirms a reported result, or disputes it."""
        bracket, match = self._require_live_match(slug, match_no)
        user_id = str(user_id)

        if match["state"] != "reported":
            raise BracketError("There is nothing to confirm on this match")
        if user_id not in (match["p1_user_id"], match["p2_user_id"]):
            raise BracketError("Only the two players in this match can confirm it")
        if user_id == match["reported_by"]:
            raise BracketError("Your opponent has to confirm the result you reported")

        if not agree:
            self._repo.update_match(
                bracket["bracket_id"],
                match_no,
                {
                    "state": "pending",
                    "reported_by": None,
                    "reported_winner_id": None,
                    "reported_at": None,
                    "expires_at": None,
                },
            )
            return {"state": "disputed"}

        self._complete(bracket, match_no, match["reported_winner_id"], resolved_by=user_id)
        return {"state": "complete"}

    def set_result(self, slug: str, match_no: int, winner_user_id, admin_id: str) -> dict:
        """Admin override: settle a match without waiting on the players."""
        bracket, match = self._require_live_match(slug, match_no)
        if match["state"] == "bye":
            raise BracketError("That match is a bye")

        winner_user_id = str(winner_user_id) if winner_user_id else None
        if winner_user_id not in (match["p1_user_id"], match["p2_user_id"]):
            raise BracketError("The winner has to be one of the two players")

        if match["state"] == "complete":
            self._clear_from(bracket, match_no)

        self._complete(bracket, match_no, winner_user_id, resolved_by=admin_id)
        return {"state": "complete"}

    def reset_match(self, slug: str, match_no: int) -> dict:
        """Admin: wipe a result and everything it decided downstream."""
        bracket, match = self._require_live_match(slug, match_no)
        self._clear_from(bracket, match_no)
        self._repo.update_match(
            bracket["bracket_id"],
            match_no,
            {
                "state": "pending",
                "winner_user_id": None,
                "winner_seed": None,
                "reported_by": None,
                "reported_winner_id": None,
                "reported_at": None,
                "expires_at": None,
                "resolved_by": None,
                "resolved_at": None,
            },
        )
        if bracket["status"] == "complete":
            self._repo.set_status(bracket["bracket_id"], "published")
        return {"state": "pending"}

    def auto_confirm_expired(self) -> list[dict]:
        """Advance reported results whose confirmation window has lapsed."""
        confirmed = []
        for row in self._repo.get_expired_reports(int(time.time())):
            bracket = self._repo.get_bracket(bracket_id=row["bracket_id"])
            if not bracket:
                continue
            try:
                self._complete(
                    bracket, row["match_no"], row["reported_winner_id"], resolved_by="auto"
                )
                confirmed.append({"slug": bracket["slug"], "match_no": row["match_no"]})
            except Exception as e:
                logger.error(
                    "Auto-confirm failed for %s match %s: %s",
                    bracket["slug"],
                    row["match_no"],
                    e,
                )
        return confirmed

    # -- Internals ------------------------------------------------

    def _require_live_match(self, slug: str, match_no: int):
        bracket = self._repo.get_bracket(slug=slug)
        if not bracket:
            raise BracketError("Bracket not found")
        if bracket["status"] == "draft":
            raise BracketError("This bracket has not been published yet")

        match = self._repo.get_match(bracket["bracket_id"], int(match_no))
        if not match:
            raise BracketError("Match not found")
        if not _is_playable(match) and match["state"] != "complete":
            raise BracketError("Both players are not decided yet")
        return bracket, match

    def _complete(self, bracket: dict, match_no: int, winner_user_id: str, resolved_by: str):
        """Record a winner and push them into the next round."""
        bracket_id = bracket["bracket_id"]
        matches = {m["match_no"]: m for m in self._repo.get_matches(bracket_id)}
        match = matches[match_no]

        winner_user_id = str(winner_user_id)
        if winner_user_id == str(match["p1_user_id"]):
            winner_seed = match["p1_seed"]
        elif winner_user_id == str(match["p2_user_id"]):
            winner_seed = match["p2_seed"]
        else:
            raise BracketError("The winner has to be one of the two players")

        match.update(
            {
                "state": "complete",
                "winner_user_id": winner_user_id,
                "winner_seed": winner_seed,
            }
        )
        self._repo.update_match(
            bracket_id,
            match_no,
            {
                "state": "complete",
                "winner_user_id": winner_user_id,
                "winner_seed": winner_seed,
                "resolved_by": resolved_by,
                "resolved_at": datetime.now().isoformat(),
                "expires_at": None,
            },
        )

        parent = advance_winner(match, matches)
        if parent:
            self._repo.update_match(
                bracket_id,
                parent["match_no"],
                {
                    f"p{match['next_slot']}_seed": winner_seed,
                    f"p{match['next_slot']}_user_id": winner_user_id,
                    f"p{match['next_slot']}_name": winner_name(match),
                },
            )
        else:
            # No next match means that was the final.
            self._repo.set_status(bracket_id, "complete")

    def _clear_from(self, bracket: dict, match_no: int):
        """Remove a winner from every later round they were carried into."""
        bracket_id = bracket["bracket_id"]
        matches = {m["match_no"]: m for m in self._repo.get_matches(bracket_id)}
        match = matches.get(match_no)

        while match and match["next_match_no"]:
            slot = match["next_slot"]
            parent = matches[match["next_match_no"]]
            self._repo.update_match(
                bracket_id,
                parent["match_no"],
                {
                    f"p{slot}_seed": None,
                    f"p{slot}_user_id": None,
                    f"p{slot}_name": None,
                    "state": "pending",
                    "winner_user_id": None,
                    "winner_seed": None,
                    "reported_by": None,
                    "reported_winner_id": None,
                    "reported_at": None,
                    "expires_at": None,
                    "resolved_by": None,
                    "resolved_at": None,
                },
            )
            match = parent

    @staticmethod
    def _opponent(match: dict, user_id: str) -> str | None:
        if str(match["p1_user_id"]) == str(user_id):
            return match["p2_name"]
        return match["p1_name"]


def _is_playable(match: dict) -> bool:
    """Both seats filled by real players, so the match can actually happen."""
    return bool(match.get("p1_seed")) and bool(match.get("p2_seed"))
