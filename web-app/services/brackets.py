"""Bracket orchestration: seeding, publishing, and player-reported results.

Drafts are admin-only. Publishing freezes the field into a match tree, after
which the two players in a match settle it between them: one reports, the
other confirms, and the winner moves on. The confirmation window mirrors the
site's existing 48-hour match confirmation flow.
"""

import json
import logging
import random
import re
import time
from datetime import datetime
from urllib.parse import urlparse

from repositories.brackets import BracketRepository
from repositories.elo import EloRepository
from repositories.matches import MatchRepository
from repositories.user_profiles import UserProfileRepository
from services.bracket_builder import (
    advance_winner,
    bracket_size_for,
    build_matches,
    champion,
    winner_name,
)
from services.curiosa import CuriosaService
from services.leaderboard import LeaderboardService
from services.paper_elo import calculate_elo
from services.sorcery_online_table import TableUnavailable, provision_match_table
from services.ticket_holders import ticket_holder_ids
from utils.card_images import attach_images

logger = logging.getLogger(__name__)

SEED_SOURCES = ("ticket_holders", "overall", "manual")


class BracketError(Exception):
    """A bracket action that cannot be carried out."""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "bracket"


class BracketService:
    def __init__(
        self,
        repo=None,
        leaderboard_service=None,
        curiosa_service=None,
        elo_repo=None,
        match_repo=None,
        profile_repo=None,
    ):
        self._repo = repo or BracketRepository()
        self._leaderboard_override = leaderboard_service
        self._curiosa_override = curiosa_service
        self._elo_repo_override = elo_repo
        self._match_repo_override = match_repo
        self._profile_repo_override = profile_repo

    @property
    def _leaderboard(self):
        """Built on demand so database paths resolve at call time."""
        return self._leaderboard_override or LeaderboardService()

    @property
    def _curiosa(self):
        return self._curiosa_override or CuriosaService()

    @property
    def _match_repo(self):
        """The online match log. Built on demand so its path resolves late."""
        return self._match_repo_override or MatchRepository()

    @property
    def _elo_repo(self):
        """The bot ladder. Built on demand so its path resolves at call time."""
        return self._elo_repo_override or EloRepository()

    @property
    def _profile_repo(self):
        """Site profiles, for the names players have chosen for themselves."""
        return self._profile_repo_override or UserProfileRepository()

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
            bracket["champion"] = None
            bracket["open_matches"] = 0
            try:
                matches = self._repo.get_matches(bracket["bracket_id"])
                bracket["champion"] = champion(matches) if matches else None
                if bracket["champion"]:
                    self._use_site_names([], [], bracket["champion"])
                bracket["open_matches"] = len(
                    [m for m in matches if m["state"] == "pending" and _is_playable(m)]
                )
            except Exception as e:
                logger.error(
                    "Could not summarise bracket %s: %s", bracket.get("slug"), e, exc_info=True
                )
        return brackets

    def _site_names(self, user_ids) -> dict:
        """What the rest of the site calls these players, by id.

        A bracket records the name a player was seeded under, but a name is
        not a result: someone who has set a display name since should be
        called by it here too, rather than by whatever handle the admin
        search happened to return. A name the player chose themselves wins,
        as it does on their profile; otherwise the ladder's name, as the
        leaderboard shows it.
        """
        ids = [str(u) for u in user_ids if u]
        if not ids:
            return {}

        names = {}
        try:
            names.update(self._elo_repo.get_display_names(ids))
        except Exception as e:
            logger.warning("Bracket name lookup failed, keeping seeded names: %s", e)
        try:
            names.update(self._profile_repo.get_custom_display_names(ids))
        except Exception as e:
            logger.warning("Bracket chosen-name lookup failed: %s", e)
        return names

    def _use_site_names(self, entrants, rounds, champion_row=None):
        ids = [e.get("user_id") for e in entrants]
        ids += [
            match.get(f"p{slot}_user_id")
            for round_data in rounds
            for match in round_data["matches"]
            for slot in (1, 2)
        ]
        if champion_row:
            ids.append(champion_row.get("user_id"))

        names = self._site_names(ids)
        if not names:
            return

        def rename(row, id_key, name_key):
            current = names.get(str(row.get(id_key) or ""))
            if current:
                row[name_key] = current

        for entrant in entrants:
            rename(entrant, "user_id", "display_name")
        for round_data in rounds:
            for match in round_data["matches"]:
                rename(match, "p1_user_id", "p1_name")
                rename(match, "p2_user_id", "p2_name")
        if champion_row:
            rename(champion_row, "user_id", "display_name")

    def get_bracket_detail(
        self,
        slug: str,
        include_drafts: bool = False,
        viewer_id=None,
        is_admin: bool = False,
    ) -> dict | None:
        bracket = self._repo.get_bracket(slug=slug)
        if not bracket:
            return None
        if bracket["status"] == "draft" and not include_drafts:
            return None

        self.auto_confirm_expired()
        bracket = self._repo.get_bracket(slug=slug)

        matches = self._repo.get_matches(bracket["bracket_id"])
        entrants = self._repo.get_entrants(bracket["bracket_id"])
        rounds = rounds_for_display(matches)

        viewer_id = str(viewer_id) if viewer_id else None
        seeds_with_decks = {d["seed"] for d in self._repo.get_decks(bracket["bracket_id"])}
        finished = bracket["status"] == "complete"

        for round_data in rounds:
            for match in round_data["matches"]:
                self._annotate_for_viewer(
                    match,
                    viewer_id=viewer_id,
                    is_admin=is_admin,
                    seeds_with_decks=seeds_with_decks,
                    finished=finished,
                )

        champion_row = champion(matches) if matches else None
        self._use_site_names(entrants, rounds, champion_row)

        return {
            "bracket": bracket,
            "entrants": entrants,
            "rounds": rounds,
            "champion": champion_row,
        }

    def _annotate_for_viewer(self, match, *, viewer_id, is_admin, seeds_with_decks, finished):
        """Attach what this viewer may do with, and see of, a match."""
        is_player = viewer_id is not None and viewer_id in (
            str(match.get("p1_user_id") or ""),
            str(match.get("p2_user_id") or ""),
        )
        settled = match["state"] in ("complete", "bye")

        match["viewer_is_player"] = is_player
        match["viewer_can_report"] = (
            is_player and match["state"] == "pending" and match["playable"]
        )
        match["viewer_can_confirm"] = (
            is_player
            and match["state"] == "reported"
            and str(match.get("reported_by") or "") != viewer_id
        )

        # A table seat is the viewer's own; nobody else is handed either link.
        seat = None
        if is_player and match.get("table_provisioned_at"):
            on_p1 = viewer_id == str(match.get("p1_user_id") or "")
            seat = match["table_p1_url"] if on_p1 else match["table_p2_url"]
        match["viewer_table_url"] = seat
        match["has_table"] = bool(match.get("table_provisioned_at")) if is_player else False

        missing = [
            match[f"p{slot}_name"]
            for slot in (1, 2)
            if match.get(f"p{slot}_seed") not in seeds_with_decks
        ]
        match["decks_missing"] = missing if is_player else []
        match["viewer_can_open_table"] = bool(
            is_player and match["playable"] and not settled and not missing
        )

        # Replays follow the decks: public once the bracket is done. The link
        # is kept the moment a table opens, but Sorcery Online has nothing to
        # serve until a game is saved, so it is only offered on a played match.
        visible_to = finished or is_admin or is_player
        match["replay_url"] = (
            match.get("replay_url") if visible_to and (settled or is_admin) else None
        )
        match["replay_public"] = bool(match.get("replay_url")) and finished

        for key in ("table_p1_url", "table_p2_url"):
            match.pop(key, None)

    def preview(self, bracket_id: int) -> dict:
        """The tree a draft would produce, without writing anything.

        Lets the admin drag the seeding around and watch the first round change
        before committing to it.
        """
        bracket = self._repo.get_bracket(bracket_id=bracket_id)
        if not bracket:
            raise BracketError("Bracket not found")

        entrants = self._repo.get_entrants(bracket_id)
        if len(entrants) < 2:
            return {"entrants": entrants, "rounds": [], "bracket_size": 0, "byes": 0}

        matches = build_matches(entrants)
        rounds = rounds_for_display(matches)
        self._use_site_names(entrants, rounds)
        return {
            "entrants": entrants,
            "rounds": rounds,
            "bracket_size": bracket_size_for(len(entrants)),
            "byes": len([m for m in matches if m["state"] == "bye"]),
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
            self._reverse_elo(bracket, match)
            self._clear_from(bracket, match_no)

        self._complete(bracket, match_no, winner_user_id, resolved_by=admin_id)
        return {"state": "complete"}

    def reset_match(self, slug: str, match_no: int) -> dict:
        """Admin: wipe a result and everything it decided downstream."""
        bracket, match = self._require_live_match(slug, match_no)
        self._reverse_elo(bracket, match)
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

    # -- Decklists ------------------------------------------------

    def eliminated_seeds(self, bracket_id: int) -> set:
        """Seeds that have lost a match, so their deck is safe to show."""
        eliminated = set()
        for match in self._repo.get_matches(bracket_id):
            if match["state"] != "complete" or match["winner_seed"] is None:
                continue
            for slot in (1, 2):
                seed = match[f"p{slot}_seed"]
                if seed is not None and seed != match["winner_seed"]:
                    eliminated.add(seed)
        return eliminated

    def submit_deck(
        self,
        slug: str,
        deck_url: str,
        actor_id: str,
        seed: int | None = None,
        is_admin: bool = False,
    ) -> dict:
        """Attach a decklist to an entrant.

        A player may only submit their own; an admin submits for any seat by
        passing the seed.
        """
        bracket = self._repo.get_bracket(slug=slug)
        if not bracket:
            raise BracketError("Bracket not found")
        if bracket["status"] == "draft":
            raise BracketError("Decks can be submitted once the bracket is published")

        entrants = self._repo.get_entrants(bracket["bracket_id"])
        if is_admin and seed is not None:
            entrant = next((e for e in entrants if e["seed"] == int(seed)), None)
        else:
            entrant = next(
                (e for e in entrants if str(e.get("user_id") or "") == str(actor_id)), None
            )
        if not entrant:
            raise BracketError("You are not in this bracket")

        deck_url = (deck_url or "").strip()
        if not deck_url:
            raise BracketError("A deck link is required")

        raw = self._curiosa.fetch_deck_data(deck_url)
        try:
            deck = json.loads(raw)
        except (TypeError, ValueError):
            deck = {}
        if not deck:
            raise BracketError("Could not read that deck - check the link is a public deck")

        avatar_list = deck.get("avatar") or []
        avatar_name = avatar_list[0].get("name") if avatar_list else None

        self._repo.upsert_deck(
            bracket["bracket_id"],
            entrant["seed"],
            {
                "user_id": entrant.get("user_id"),
                "deck_url": deck_url,
                "deck_name": deck.get("name"),
                "avatar_name": avatar_name,
                "deck_json": json.dumps(deck),
                "submitted_by": str(actor_id),
            },
        )

        return {
            "seed": entrant["seed"],
            "display_name": entrant["display_name"],
            "deck_name": deck.get("name"),
            "avatar_name": avatar_name,
        }

    def get_deck_roster(self, slug: str, viewer_id=None, is_admin: bool = False) -> dict | None:
        """Every entrant, whether they have submitted, and who can see it.

        A deck stays hidden until its owner is knocked out or the bracket is
        over - other than to the player themselves and to admins.
        """
        bracket = self._repo.get_bracket(slug=slug)
        if not bracket:
            return None
        if bracket["status"] == "draft" and not is_admin:
            return None

        entrants = self._repo.get_entrants(bracket["bracket_id"])
        decks = {d["seed"]: d for d in self._repo.get_decks(bracket["bracket_id"])}
        eliminated = self.eliminated_seeds(bracket["bracket_id"])
        finished = bracket["status"] == "complete"
        viewer_id = str(viewer_id) if viewer_id else None

        players = []
        for entrant in entrants:
            deck = decks.get(entrant["seed"])
            is_out = entrant["seed"] in eliminated
            is_owner = viewer_id is not None and str(entrant.get("user_id") or "") == viewer_id
            visible = bool(deck) and (is_admin or is_owner or is_out or finished)

            # Say *why* a deck can be seen, not just that it can. A player
            # looking at their own row would otherwise read "revealed" and
            # think the whole server could see it.
            if not deck:
                visibility = "none"
            elif is_out or finished:
                visibility = "public"
            elif is_owner:
                visibility = "owner"
            elif is_admin:
                visibility = "admin"
            else:
                visibility = "hidden"

            players.append(
                {
                    "seed": entrant["seed"],
                    "user_id": entrant.get("user_id"),
                    "display_name": entrant["display_name"],
                    "avatar": entrant.get("avatar"),
                    "provider": entrant.get("provider"),
                    "eliminated": is_out,
                    "has_deck": bool(deck),
                    "deck_visible": visible,
                    "visibility": visibility,
                    "deck_url": deck["deck_url"] if (deck and visible) else None,
                    "deck_name": deck["deck_name"] if (deck and visible) else None,
                    "avatar_name": deck["avatar_name"] if (deck and visible) else None,
                    "submitted_at": deck["submitted_at"] if deck else None,
                    "can_submit": is_owner and bracket["status"] == "published",
                }
            )

        self._use_site_names(players, [])

        return {
            "bracket": {
                "slug": bracket["slug"],
                "name": bracket["name"],
                "status": bracket["status"],
            },
            "players": players,
            "submitted": len([p for p in players if p["has_deck"]]),
            "missing": len([p for p in players if not p["has_deck"]]),
        }

    def get_deck(self, slug: str, seed: int, viewer_id=None, is_admin: bool = False) -> dict:
        """One entrant's decklist, if the viewer is allowed to see it."""
        roster = self.get_deck_roster(slug, viewer_id=viewer_id, is_admin=is_admin)
        if roster is None:
            raise BracketError("Bracket not found")

        player = next((p for p in roster["players"] if p["seed"] == int(seed)), None)
        if not player:
            raise BracketError("Not in this bracket")
        if not player["has_deck"]:
            raise BracketError("No deck submitted")
        if not player["deck_visible"]:
            raise BracketError("This deck stays hidden until the player is knocked out")

        bracket = self._repo.get_bracket(slug=slug)
        stored = self._repo.get_deck(bracket["bracket_id"], int(seed))
        try:
            deck = json.loads(stored["deck_json"] or "{}")
        except (TypeError, ValueError):
            deck = {}

        # Curiosa stores absolute CDN urls, which /card-images cannot serve.
        # Resolve every card against the site's own image set instead.
        for section in ("avatar", "spellbook", "atlas", "sideboard"):
            attach_images(deck.get(section))

        return {"player": player, "deck": deck}

    def delete_deck(self, slug: str, seed: int) -> bool:
        bracket = self._repo.get_bracket(slug=slug)
        if not bracket:
            raise BracketError("Bracket not found")
        return self._repo.delete_deck(bracket["bracket_id"], int(seed))

    # -- Finishes -------------------------------------------------

    # A placement is the position a single-elimination finish is worth: losing
    # the final is 2nd, the semis 3rd, the quarters 5th, and so on.
    FINISH_LABELS = ((1, "Champion"), (2, "Finalist"), (4, "Top 4"), (8, "Top 8"))

    @staticmethod
    def finish_label(placement: int | None) -> str | None:
        """What a placement is called. Anything deeper simply made the cut."""
        if not placement:
            return None
        for limit, label in BracketService.FINISH_LABELS:
            if placement <= limit:
                return label
        return "Top cut"

    def placements(self, bracket_id: int) -> dict:
        """{seed: placement} for everyone whose run has ended.

        Players still alive have no placement yet, so they are left out.
        """
        matches = self._repo.get_matches(bracket_id)
        rounds = [m["round"] for m in matches if m["state"] != "empty"]
        if not rounds:
            return {}
        last_round = max(rounds)

        placements = {}
        for match in matches:
            if match["state"] != "complete" or match["winner_seed"] is None:
                continue
            for slot in (1, 2):
                seed = match[f"p{slot}_seed"]
                if seed is None or seed == match["winner_seed"]:
                    continue
                # Knocked out in round r of an R-round bracket.
                placements[seed] = 2 ** (last_round - match["round"]) + 1

            if match["round"] == last_round:
                placements[match["winner_seed"]] = 1

        return placements

    def get_player_marks(self) -> dict:
        """Postseason honours per player, for showing beside their name.

        Only finished brackets count - a run that is still going has not been
        placed yet.
        """
        marks = {}
        for bracket in self._repo.list_brackets(published_only=True):
            if bracket["status"] != "complete":
                continue

            placements = self.placements(bracket["bracket_id"])
            for entrant in self._repo.get_entrants(bracket["bracket_id"]):
                user_id = str(entrant.get("user_id") or "")
                placement = placements.get(entrant["seed"])
                if not user_id or not placement:
                    continue

                entry = marks.setdefault(user_id, {"wins": 0, "best": None, "entries": []})
                if placement == 1:
                    entry["wins"] += 1
                if entry["best"] is None or placement < entry["best"]:
                    entry["best"] = placement
                entry["entries"].append(
                    {
                        "slug": bracket["slug"],
                        "name": bracket["name"],
                        "placement": placement,
                        "label": self.finish_label(placement),
                    }
                )

        for entry in marks.values():
            entry["best_label"] = self.finish_label(entry["best"])
        return marks

    def get_player_postseason(self, user_id) -> list[dict]:
        """Every bracket this player has been in, newest first."""
        user_id = str(user_id)
        out = []

        for bracket in self._repo.list_brackets(published_only=True):
            entrants = self._repo.get_entrants(bracket["bracket_id"])
            entrant = next(
                (e for e in entrants if str(e.get("user_id") or "") == user_id), None
            )
            if not entrant:
                continue

            placement = self.placements(bracket["bracket_id"]).get(entrant["seed"])
            matches = self._repo.get_matches(bracket["bracket_id"])
            wins = len(
                [m for m in matches if m["state"] == "complete" and str(m["winner_user_id"] or "") == user_id]
            )
            losses = len(
                [
                    m
                    for m in matches
                    if m["state"] == "complete"
                    and m["winner_user_id"]
                    and str(m["winner_user_id"]) != user_id
                    and user_id in (str(m["p1_user_id"] or ""), str(m["p2_user_id"] or ""))
                ]
            )

            out.append(
                {
                    "slug": bracket["slug"],
                    "name": bracket["name"],
                    "status": bracket["status"],
                    "entrants": bracket["entrant_count"],
                    "seed": entrant["seed"],
                    "placement": placement,
                    "label": self.finish_label(placement) or "Still in",
                    "wins": wins,
                    "losses": losses,
                    "played_at": bracket["published_at"] or bracket["created_at"],
                }
            )

        return out

    # -- Sorcery Online tables ------------------------------------

    def open_table(self, slug: str, match_no: int, user_id: str) -> dict:
        """Open (or re-open) the Sorcery Online table for a pairing.

        Both decks are preloaded, so both players must have submitted one. The
        table is provisioned once and each player is handed only their own seat.
        """
        bracket, match = self._require_live_match(slug, match_no)
        user_id = str(user_id)

        if user_id not in (str(match["p1_user_id"] or ""), str(match["p2_user_id"] or "")):
            raise BracketError("Only the two players in this match can open the table")
        if match["state"] in ("complete", "bye"):
            raise BracketError("This match is already settled")

        on_p1 = user_id == str(match["p1_user_id"] or "")

        # Already provisioned: hand back this player's seat rather than asking
        # Sorcery Online for a second table.
        if match["table_provisioned_at"]:
            seat = match["table_p1_url"] if on_p1 else match["table_p2_url"]
            if seat:
                return {"game_url": seat, "reused": True}

        decks = {d["seed"]: d for d in self._repo.get_decks(bracket["bracket_id"])}
        missing = [
            match[f"p{slot}_name"] for slot in (1, 2) if match[f"p{slot}_seed"] not in decks
        ]
        if missing:
            raise BracketError(
                f"{' and '.join(missing)} still need to submit a decklist before the table opens"
            )

        names = self._site_names([match[f"p{slot}_user_id"] for slot in (1, 2)])
        players = [
            {
                "user_id": match[f"p{slot}_user_id"],
                "display_name": names.get(str(match[f"p{slot}_user_id"] or ""))
                or match[f"p{slot}_name"],
                "deck_url": decks[match[f"p{slot}_seed"]]["deck_url"],
            }
            for slot in (1, 2)
        ]
        if not all(p["user_id"] for p in players):
            raise BracketError("Both players need a site account to open a table")

        try:
            table = provision_match_table(
                f"bracket-{bracket['bracket_id']}-m{match_no}", players
            )
        except TableUnavailable as e:
            raise BracketError(str(e)) from e

        seats = table.get("seats") or {}
        fields = {
            "table_provisioned_at": datetime.now().isoformat(),
            "table_p1_url": seats.get(str(match["p1_user_id"])),
            "table_p2_url": seats.get(str(match["p2_user_id"])),
        }

        # Sorcery Online hands back the replay url with the table. It only
        # serves a recording once a game has been saved, but the link itself is
        # stable, so keep it now and let the usual rule decide when to show it.
        # An admin who has already filed one keeps theirs.
        replay_url = table.get("replay_url")
        if replay_url and not match.get("replay_url"):
            fields["replay_url"] = replay_url
            fields["replay_added_by"] = "sorcery-online"
            fields["replay_added_at"] = datetime.now().isoformat()

        self._repo.update_match(bracket["bracket_id"], match_no, fields)

        return {
            "game_url": seats.get(str(user_id)),
            "reused": False,
        }

    # -- Replays --------------------------------------------------

    REPLAY_HOSTS = ("playsorceryonline.com",)

    def set_replay(self, slug: str, match_no: int, replay_url: str, admin_id: str) -> dict:
        """Attach a Sorcery Online replay to a match. Public when the bracket ends."""
        bracket, match = self._require_live_match(slug, match_no)

        replay_url = (replay_url or "").strip()
        if not replay_url:
            raise BracketError("A replay link is required")

        host = (urlparse(replay_url).hostname or "").lower().removeprefix("www.")
        if host not in self.REPLAY_HOSTS:
            raise BracketError("Replay links have to be Sorcery Online links")

        self._repo.update_match(
            bracket["bracket_id"],
            match_no,
            {
                "replay_url": replay_url,
                "replay_added_by": str(admin_id),
                "replay_added_at": datetime.now().isoformat(),
            },
        )
        return {"replay_url": replay_url, "public": bracket["status"] == "complete"}

    def clear_replay(self, slug: str, match_no: int) -> bool:
        bracket, match = self._require_live_match(slug, match_no)
        if not match["replay_url"]:
            return False
        self._repo.update_match(
            bracket["bracket_id"],
            match_no,
            {"replay_url": None, "replay_added_by": None, "replay_added_at": None},
        )
        return True

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

        self._apply_elo(bracket, match)
        self._record_match(bracket, match)

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

    K_FACTOR = 32

    def _apply_elo(self, bracket: dict, match: dict):
        try:
            self._apply_elo_inner(bracket, match)
        except Exception as e:
            logger.error(
                "Bracket %s match %s: rating failed, result still stands: %s",
                bracket.get("slug"), match.get("match_no"), e,
            )

    def _reverse_elo(self, bracket: dict, match: dict):
        try:
            self._withdraw_match(bracket, match)
            self._reverse_elo_inner(bracket, match)
        except Exception as e:
            logger.error(
                "Bracket %s match %s: rating reversal failed: %s",
                bracket.get("slug"), match.get("match_no"), e,
            )

    def _apply_elo_inner(self, bracket: dict, match: dict):
        """Move both players' online lifetime ELO for a decided bracket match.

        Postseason games count as ranked, but only against lifetime ELO - the
        event ladder is left alone. Byes never get here, and entrants without a
        site account cannot be rated.
        """
        if match.get("elo_applied_at"):
            return

        winner_id = str(match["winner_user_id"] or "")
        loser_id = str(
            match["p2_user_id"] if winner_id == str(match["p1_user_id"] or "") else match["p1_user_id"]
            or ""
        )
        if not winner_id or not loser_id or winner_id == loser_id:
            return

        elo_repo = self._elo_repo
        try:
            winner_elo = elo_repo.get_user_elo(winner_id)
            loser_elo = elo_repo.get_user_elo(loser_id)
        except Exception as e:
            logger.warning("Bracket ELO lookup failed: %s", e)
            return
        if winner_elo is None or loser_elo is None:
            logger.info(
                "Bracket %s match %s: no ladder rating for one of the players, ELO skipped",
                bracket["slug"], match["match_no"],
            )
            return

        winner_new = calculate_elo(winner_elo, loser_elo, True, k=self.K_FACTOR)
        loser_new = calculate_elo(loser_elo, winner_elo, False, k=self.K_FACTOR)

        try:
            # Rating only. The names on a bracket were recorded when it was
            # seeded, so writing them back would rename a player who has
            # since chosen a different one.
            elo_repo.set_user_elo(winner_id, winner_new)
            elo_repo.set_user_elo(loser_id, loser_new)
        except Exception as e:
            logger.error("Bracket ELO update failed: %s", e)
            return

        self._repo.update_match(
            bracket["bracket_id"],
            match["match_no"],
            {
                "elo_applied_at": datetime.now().isoformat(),
                "winner_elo_change": winner_new - winner_elo,
                "loser_elo_change": loser_new - loser_elo,
            },
        )

    def _reverse_elo_inner(self, bracket: dict, match: dict):
        """Give back what a result took, when it is reset or corrected.

        The deltas are stored per match, so undoing restores exactly the points
        that were moved even if other games have happened since.
        """
        if not match.get("elo_applied_at"):
            return

        winner_id = str(match["winner_user_id"] or "")
        if not winner_id:
            return
        on_p1 = winner_id == str(match["p1_user_id"] or "")
        loser_id = str((match["p2_user_id"] if on_p1 else match["p1_user_id"]) or "")

        elo_repo = self._elo_repo
        for user_id, change in (
            (winner_id, match.get("winner_elo_change") or 0),
            (loser_id, match.get("loser_elo_change") or 0),
        ):
            try:
                current = elo_repo.get_user_elo(user_id)
                if current is None or not change:
                    continue
                elo_repo.set_user_elo(user_id, current - change)
            except Exception as e:
                logger.error("Bracket ELO reversal failed for %s: %s", user_id, e)

        self._repo.update_match(
            bracket["bracket_id"],
            match["match_no"],
            {"elo_applied_at": None, "winner_elo_change": None, "loser_elo_change": None},
        )

    MATCH_SOURCE = "Bracket"

    def _record_match(self, bracket: dict, match: dict):
        """Log a settled bracket game as a played match.

        Without this a postseason win moves a player's rating while leaving no
        trace in their history, so the change looks like it came from nowhere.
        The decks are the ones submitted to the bracket.
        """
        try:
            if match.get("match_record_id"):
                return

            stored = self._repo.get_match(bracket["bracket_id"], match["match_no"])
            winner_id = str(stored["winner_user_id"] or "")
            if not winner_id:
                return
            on_p1 = winner_id == str(stored["p1_user_id"] or "")
            loser_id = str((stored["p2_user_id"] if on_p1 else stored["p1_user_id"]) or "")
            if not loser_id:
                return

            decks = {d["seed"]: d for d in self._repo.get_decks(bracket["bracket_id"])}
            winner_deck = decks.get(stored["p1_seed"] if on_p1 else stored["p2_seed"]) or {}
            loser_deck = decks.get(stored["p2_seed"] if on_p1 else stored["p1_seed"]) or {}

            elo_repo = self._elo_repo
            # Under the name the player goes by now, not the one the bracket
            # was seeded with.
            names = self._site_names([winner_id, loser_id])
            row_id = self._match_repo.insert_match(
                {
                    "reporter_id": stored.get("resolved_by"),
                    "winner_id": winner_id,
                    "winner_display_name": names.get(winner_id)
                    or (stored["p1_name"] if on_p1 else stored["p2_name"]),
                    "losser_id": loser_id,
                    "losser_display_name": names.get(loser_id)
                    or (stored["p2_name"] if on_p1 else stored["p1_name"]),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "match_comment": f"{bracket['name']} - {stored['round_title']}",
                    "curiosa_url_winner": winner_deck.get("deck_url"),
                    "curiosa_url_loser": loser_deck.get("deck_url"),
                    "json_deck_data_winner": winner_deck.get("deck_json"),
                    "json_deck_data_loser": loser_deck.get("deck_json"),
                    "winner_elo_change": stored.get("winner_elo_change"),
                    "loser_elo_change": stored.get("loser_elo_change"),
                    "winner_lifetime_elo_after": elo_repo.get_user_elo(winner_id),
                    "loser_lifetime_elo_after": elo_repo.get_user_elo(loser_id),
                    "source": self.MATCH_SOURCE,
                    "match_type": "ranked",
                }
            )
            self._repo.update_match(
                bracket["bracket_id"], match["match_no"], {"match_record_id": row_id}
            )
        except Exception as e:
            logger.error(
                "Bracket %s match %s: could not log the match, result still stands: %s",
                bracket.get("slug"), match.get("match_no"), e,
            )

    def _withdraw_match(self, bracket: dict, match: dict):
        """Take the logged match back when its result is undone."""
        row_id = match.get("match_record_id")
        if not row_id:
            return
        self._match_repo.delete_match_row(row_id)
        self._repo.update_match(
            bracket["bracket_id"], match["match_no"], {"match_record_id": None}
        )

    def _clear_from(self, bracket: dict, match_no: int):
        """Remove a winner from every later round they were carried into."""
        bracket_id = bracket["bracket_id"]
        matches = {m["match_no"]: m for m in self._repo.get_matches(bracket_id)}
        match = matches.get(match_no)

        while match and match["next_match_no"]:
            slot = match["next_slot"]
            parent = matches[match["next_match_no"]]
            # The parent's own result is being wiped, so its rating change goes
            # back too - otherwise a reset leaves points behind for a game that
            # no longer exists.
            self._reverse_elo(bracket, parent)
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


def rounds_for_display(matches: list[dict]) -> list[dict]:
    """Group matches into rounds for the bracket view.

    Byes are not drawn. A player with a first-round bye has no match to show -
    they simply appear in round two, tagged as having had one. So a 24-player
    field reads as eight first-round pairs, with the top eight seeds waiting in
    round two, rather than sixteen cards half of which are placeholders.
    """
    from_bye = {}
    for match in matches:
        if match["state"] == "bye" and match.get("next_match_no"):
            from_bye[(match["next_match_no"], match["next_slot"])] = True

    rounds = {}
    for match in matches:
        if match["state"] in ("empty", "bye"):
            continue
        bucket = rounds.setdefault(
            match["round"],
            {"round": match["round"], "title": match["round_title"], "matches": []},
        )
        bucket["matches"].append(
            {
                **match,
                "playable": _is_playable(match),
                "p1_from_bye": from_bye.get((match["match_no"], 1), False),
                "p2_from_bye": from_bye.get((match["match_no"], 2), False),
            }
        )

    return [rounds[key] for key in sorted(rounds) if rounds[key]["matches"]]
