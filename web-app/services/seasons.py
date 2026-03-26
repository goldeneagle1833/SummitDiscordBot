"""Business logic for user-created seasons."""

import logging
from datetime import date, datetime

from repositories.seasons import SeasonsRepository

logger = logging.getLogger(__name__)


class SeasonsService:
    """Service layer for season creation, membership, management, and ELO updates."""

    def __init__(self):
        self.repo = SeasonsRepository()
        self.repo.ensure_tables()

    # ── US1: Create Season ───────────────────────────────────────

    def create_season(self, creator_id, creator_display_name, title,
                      description=None, start_date=None, end_date=None,
                      k_value=32, base_elo=1500, max_members=None,
                      region=None):
        # Validate title
        if not title or not title.strip():
            raise ValueError("Title is required")
        title = title.strip()
        if len(title) > 100:
            raise ValueError("Title must be 100 characters or less")

        # Validate description
        if description:
            description = description.strip()
            if len(description) > 500:
                raise ValueError("Description must be 500 characters or less")
            if not description:
                description = None

        # Validate dates
        if not start_date or not end_date:
            raise ValueError("Start date and end date are required")
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError("Dates must be in YYYY-MM-DD format")

        if start < date.today():
            raise ValueError("Start date must be today or in the future")
        if end < start:
            raise ValueError("End date must be on or after start date")

        # Validate k_value
        if k_value is None:
            k_value = 32
        k_value = int(k_value)
        if not 1 <= k_value <= 64:
            raise ValueError("K-value must be between 1 and 64")

        # Validate base_elo
        if base_elo is None:
            base_elo = 1500
        base_elo = int(base_elo)
        if not 0 <= base_elo <= 3000:
            raise ValueError("Base ELO must be between 0 and 3000")

        # Validate max_members
        if max_members is not None:
            max_members = int(max_members)
            if max_members < 2:
                raise ValueError("Max members must be at least 2")

        # Validate region
        if region:
            region = region.strip()
            if len(region) > 100:
                raise ValueError("Region must be 100 characters or less")
            if not region:
                region = None

        # One-season constraint
        current = self.repo.get_user_active_season(creator_id)
        if current:
            raise ValueError(
                "You are already in a season. Leave your current season "
                "before creating a new one."
            )

        # Create season + auto-enroll creator
        season_id = self.repo.create_season(
            creator_id, creator_display_name, title, description,
            start_date, end_date, k_value, base_elo, max_members, region,
        )
        self.repo.add_member(season_id, creator_id, creator_display_name,
                             base_elo)
        logger.info(
            "Season %d '%s' created by %s", season_id, title, creator_id
        )
        return season_id

    # ── US2: Join / Search Season ────────────────────────────────

    def search_seasons(self, query, user_id, include_ended=False):
        results = self.repo.search_seasons(query, user_id, include_ended=include_ended)
        today = date.today().isoformat()
        for r in results:
            if r["status"] == "ended":
                pass  # keep "ended"
            elif r["start_date"] > today:
                r["status"] = "upcoming"
            else:
                r["status"] = "active"
        return results

    def join_season(self, user_id, display_name, season_id):
        season = self.repo.get_season_by_id(season_id)
        if not season:
            raise ValueError("Season not found")
        if season["status"] != "active":
            raise ValueError("Season not found")
        if season["end_date"] < date.today().isoformat():
            raise ValueError("Season has ended")

        # One-season constraint
        current = self.repo.get_user_active_season(user_id)
        if current:
            raise ValueError(
                "You are already in a season. Leave your current season first."
            )

        # Max members check
        if season["max_members"] is not None:
            count = self.repo.get_member_count(season_id)
            if count >= season["max_members"]:
                raise ValueError("This season is full")

        self.repo.add_member(season_id, user_id, display_name,
                             season["base_elo"])
        logger.info("User %s joined season %d", user_id, season_id)

    # ── US5: Player Season / Leave ───────────────────────────────

    def get_player_season(self, player_id):
        membership = self.repo.get_user_active_season(player_id)
        if not membership:
            return None

        season = self.repo.get_season_by_id(membership["season_id"])
        if not season:
            return None

        members = self.repo.get_season_members(membership["season_id"])
        member_count = len(members)

        # Find this player's rank
        rank = None
        for m in members:
            if m["user_id"] == str(player_id):
                rank = m["rank"]
                break

        today = date.today().isoformat()
        status = "upcoming" if season["start_date"] > today else "active"

        return {
            "season_id": season["season_id"],
            "title": season["title"],
            "description": season["description"],
            "start_date": season["start_date"],
            "end_date": season["end_date"],
            "season_elo": membership["season_elo"],
            "wins": membership["wins"],
            "losses": membership["losses"],
            "rank": rank,
            "member_count": member_count,
            "max_members": season["max_members"],
            "region": season["region"],
            "k_value": season["k_value"],
            "is_creator": str(player_id) == season["creator_id"],
            "status": status,
        }

    def leave_season(self, user_id, season_id):
        season = self.repo.get_season_by_id(season_id)
        if not season:
            raise ValueError("Season not found")

        if str(user_id) == season["creator_id"]:
            raise ValueError(
                "Season creators cannot leave. Use End Season or Delete Season instead."
            )

        # Verify membership
        membership = self.repo.get_user_active_season(user_id)
        if not membership or membership["season_id"] != season_id:
            raise ValueError("You are not a member of this season")

        self.repo.remove_member(season_id, user_id)
        logger.info("User %s left season %d", user_id, season_id)

    # ── US4: Season Management (Creator) ─────────────────────────

    def modify_season(self, user_id, season_id, **fields):
        season = self.repo.get_season_by_id(season_id)
        if not season:
            raise ValueError("Season not found")
        if str(user_id) != season["creator_id"]:
            raise ValueError("Only the season creator can modify this season")

        # Validate dates if provided
        start = fields.get("start_date") or season["start_date"]
        end = fields.get("end_date") or season["end_date"]
        if end < start:
            raise ValueError("End date must be on or after start date")

        # Validate k_value
        if "k_value" in fields and fields["k_value"] is not None:
            kv = int(fields["k_value"])
            if not 1 <= kv <= 64:
                raise ValueError("K-value must be between 1 and 64")
            fields["k_value"] = kv

        # Validate max_members
        if "max_members" in fields and fields["max_members"] is not None:
            mm = int(fields["max_members"])
            current_count = self.repo.get_member_count(season_id)
            if mm < current_count:
                raise ValueError(
                    f"Max members cannot be less than current member count ({current_count})"
                )
            fields["max_members"] = mm

        # Validate description
        if "description" in fields and fields["description"]:
            if len(fields["description"]) > 500:
                raise ValueError("Description must be 500 characters or less")

        self.repo.update_season(season_id, **fields)
        logger.info("Season %d modified by %s", season_id, user_id)

    def end_season(self, user_id, season_id):
        season = self.repo.get_season_by_id(season_id)
        if not season:
            raise ValueError("Season not found")
        if str(user_id) != season["creator_id"]:
            raise ValueError("Only the season creator can end this season")
        if season["status"] != "active":
            raise ValueError("Season is not active")

        self.repo.end_season(season_id)
        logger.info("Season %d ended by %s", season_id, user_id)

    def delete_season(self, user_id, season_id):
        season = self.repo.get_season_by_id(season_id)
        if not season:
            raise ValueError("Season not found")
        if str(user_id) != season["creator_id"]:
            raise ValueError("Only the season creator can delete this season")

        self.repo.delete_season(season_id)
        logger.info("Season %d deleted by %s", season_id, user_id)

    def kick_member(self, creator_id, season_id, target_user_id):
        season = self.repo.get_season_by_id(season_id)
        if not season:
            raise ValueError("Season not found")
        if str(creator_id) != season["creator_id"]:
            raise ValueError("Only the season creator can kick members")
        if str(target_user_id) == season["creator_id"]:
            raise ValueError("You cannot kick yourself from your own season")

        # Verify target is a member
        members = self.repo.get_season_members(season_id)
        is_member = any(m["user_id"] == str(target_user_id) for m in members)
        if not is_member:
            raise ValueError("User is not a member of this season")

        self.repo.remove_member(season_id, target_user_id)
        logger.info(
            "User %s kicked from season %d by %s",
            target_user_id, season_id, creator_id,
        )

    def get_season_members(self, season_id):
        return self.repo.get_season_members(season_id)

    # ── US3: Season ELO Tracking ─────────────────────────────────

    def update_season_elos(self, winner_id, loser_id, match_id,
                           is_repeat_matchup, match_data):
        if is_repeat_matchup:
            return []

        season = self.repo.get_shared_active_season(winner_id, loser_id)
        if not season:
            return []

        season_id = season["season_id"]
        k = season["k_value"]

        winner_elo = self.repo.get_member_elo(season_id, winner_id)
        loser_elo = self.repo.get_member_elo(season_id, loser_id)
        if winner_elo is None or loser_elo is None:
            return []

        # Standard ELO formula
        expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
        expected_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))

        new_winner_elo = round(winner_elo + k * (1 - expected_winner))
        new_loser_elo = round(loser_elo + k * (0 - expected_loser))

        winner_change = new_winner_elo - winner_elo
        loser_change = new_loser_elo - loser_elo

        # Update member ELOs and win/loss counts
        self.repo.update_member_elo_and_record(
            season_id, winner_id, new_winner_elo, is_winner=True
        )
        self.repo.update_member_elo_and_record(
            season_id, loser_id, new_loser_elo, is_winner=False
        )

        # Insert full match record
        self.repo.insert_season_match_record(
            season_id, match_id, match_data,
            winner_elo, new_winner_elo, winner_change,
            loser_elo, new_loser_elo, loser_change,
        )

        logger.info(
            "Season %d ELO updated: %s %+d (%d→%d), %s %+d (%d→%d)",
            season_id, winner_id, winner_change, winner_elo, new_winner_elo,
            loser_id, loser_change, loser_elo, new_loser_elo,
        )

        return [{
            "season_id": season_id,
            "season_title": season["title"],
            "winner_change": winner_change,
            "loser_change": loser_change,
        }]
