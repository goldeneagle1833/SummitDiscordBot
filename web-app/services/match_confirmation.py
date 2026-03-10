"""Service layer for match confirmation business logic."""

import datetime
import logging
import re
from typing import Optional

from repositories.match_confirmation import MatchConfirmationRepository
from repositories.user_profiles import UserProfileRepository

# Configure logger for match reporting operations
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MatchConfirmationService:
    """Business logic for match confirmations."""

    def __init__(
        self,
        repository: Optional[MatchConfirmationRepository] = None,
        user_repo: Optional[UserProfileRepository] = None
    ):
        self.repo = repository or MatchConfirmationRepository()
        self.user_repo = user_repo or UserProfileRepository()

    def create_match_report(
        self,
        submitter_id: int,
        opponent_identification: dict,
        match_result: dict,
        decks: dict,
    ) -> dict:
        """
        Create a new match report and confirmation request.

        Args:
            submitter_id: Discord user ID of submitter
            opponent_identification: {"method": "discord_username"|"discord_id"|"lfg_lookup", "value": ...}
            match_result: {"winner": "self"|"opponent", "final_life": {"self": int, "opponent": int}}
            decks: {"self_deck_url": str|None, "opponent_deck_url": str|None}

        Returns:
            dict: {"success": bool, "confirmation_id": int, "expires_at": int, "opponent": dict}

        Raises:
            ValueError: If validation fails
            RuntimeError: If opponent not found or database error
        """
        # Stub implementation - to be completed in T045-T047
        raise NotImplementedError("create_match_report not yet implemented")

    def process_confirmation(
        self, confirmation_id: int, action: str, user_id: int
    ) -> dict:
        """
        Process a match confirmation (confirm or dispute).

        Args:
            confirmation_id: ID of confirmation to process
            action: 'confirm' or 'dispute'
            user_id: Discord user ID of user taking action

        Returns:
            dict: {"success": bool, "message": str, "elo_changes": dict | None}

        Raises:
            ValueError: If confirmation not found or already processed
            RuntimeError: If ELO update fails
        """
        # Stub implementation - to be completed in T072-T075
        raise NotImplementedError("process_confirmation not yet implemented")

    def auto_confirm_expired(self) -> int:
        """
        Auto-confirm all expired pending confirmations.

        Returns:
            int: Count of confirmations auto-confirmed
        """
        # Stub implementation - to be completed in T076
        raise NotImplementedError("auto_confirm_expired not yet implemented")

    def _finalize_confirmed_match(self, confirmation: dict) -> dict:
        """
        Internal helper to trigger ELO update and create match record.

        Args:
            confirmation: Confirmation record dict

        Returns:
            dict: ELO changes {"winner": {...}, "loser": {...}}
        """
        # Stub implementation - to be completed in T073-T075
        raise NotImplementedError("_finalize_confirmed_match not yet implemented")

    def validate_match_report_input(
        self,
        submitter_id: str,
        opponent_id: str,
        result: str,
        went_first: str,
        submitter_deck_url: Optional[str] = None,
        opponent_deck_url: Optional[str] = None,
    ) -> dict:
        """
        Validate all inputs for a match report submission.

        Args:
            submitter_id: Discord user ID of submitter
            opponent_id: Discord user ID of opponent
            result: Match result ('won' or 'lost')
            went_first: Turn order ('submitter' or 'opponent')
            submitter_deck_url: Optional Curiosa.io deck URL for submitter
            opponent_deck_url: Optional Curiosa.io deck URL for opponent

        Returns:
            dict: {"valid": bool, "errors": dict} where errors maps field names to error messages

        Validation Rules:
            - opponent_id must not equal submitter_id (no self-reporting)
            - result must be 'won' or 'lost'
            - went_first must be 'submitter' or 'opponent'
            - deck URLs (if provided) must match Curiosa.io pattern
        """
        errors = {}

        # Validate opponent selection (no self-reporting)
        if not opponent_id:
            errors["opponent_id"] = "Opponent is required"
        elif str(submitter_id) == str(opponent_id):
            errors["opponent_id"] = "Cannot report a match against yourself"

        # Validate result
        if result not in ("won", "lost"):
            errors["result"] = "Result must be 'won' or 'lost'"

        # Validate turn order
        if went_first not in ("submitter", "opponent"):
            errors["went_first"] = "Turn order must be 'submitter' or 'opponent'"

        # Validate deck URLs
        # Pattern supports: http/https, optional www, alphanumeric ID with hyphens/underscores, optional query params
        deck_url_pattern = r"^https?://(www\.)?curiosa\.io/decks/[a-zA-Z0-9_-]+(\?.*)?$"

        # Submitter deck URL is now REQUIRED
        if not submitter_deck_url:
            errors["submitter_deck_url"] = "Your deck URL is required"
        elif not re.match(deck_url_pattern, submitter_deck_url):
            errors[
                "submitter_deck_url"
            ] = "Invalid Curiosa.io deck URL format. Expected: https://curiosa.io/decks/[deck-id]"

        # Opponent deck URL is optional (provided during confirmation)
        if opponent_deck_url:
            if not re.match(deck_url_pattern, opponent_deck_url):
                errors[
                    "opponent_deck_url"
                ] = "Invalid Curiosa.io deck URL format. Expected: https://curiosa.io/decks/[deck-id]"

        return {"valid": len(errors) == 0, "errors": errors}

    def calculate_winner_loser(
        self, submitter_id: str, opponent_id: str, result: str
    ) -> dict:
        """
        Calculate winner and loser IDs based on match result from submitter's perspective.

        Args:
            submitter_id: Discord user ID of submitter
            opponent_id: Discord user ID of opponent
            result: Match result from submitter's perspective ('won' or 'lost')

        Returns:
            dict: {"winner_id": str, "loser_id": str}

        Example:
            >>> calculate_winner_loser("123", "456", "won")
            {"winner_id": "123", "loser_id": "456"}

            >>> calculate_winner_loser("123", "456", "lost")
            {"winner_id": "456", "loser_id": "123"}
        """
        if result == "won":
            winner_id = str(submitter_id)
            loser_id = str(opponent_id)
        else:  # result == "lost"
            winner_id = str(opponent_id)
            loser_id = str(submitter_id)

        logger.info(
            f"Match result calculated: submitter={submitter_id}, opponent={opponent_id}, "
            f"result={result} → winner={winner_id}, loser={loser_id}"
        )

        return {"winner_id": winner_id, "loser_id": loser_id}

    def search_opponents(
        self, current_user_id: str, query: str, limit: int = 10
    ) -> list[dict]:
        """
        Search for opponents using 2-tier approach: recent opponents → all users.

        Prioritizes users the current user has recently played against,
        then searches all user profiles by display name.

        Args:
            current_user_id: Discord user ID of current user
            query: Search query string
            limit: Maximum number of results

        Returns:
            list[dict]: List of opponents with format:
                {
                    "user_id": str,
                    "display_name": str,
                    "avatar": str | None,
                    "recent_match_count": int,
                    "last_matched_at": int | None,
                    "is_recent": bool
                }
        """
        # Tier 1: Get recent opponents from match history
        # Works for both Discord and Google users (after normalizing to numeric ID)
        recent_opponents = []
        try:
            numeric_user_id = self._normalize_user_id(current_user_id)
            recent_opponents = self.repo.get_recent_lfg_opponents(
                user_id=numeric_user_id, limit=limit
            )
        except (ValueError, Exception) as e:
            # User ID format is invalid or database error, skip recent opponents lookup
            logger.debug(
                f"Skipping recent opponents lookup for user_id {current_user_id}: {e}"
            )

        # Build map of recent opponent IDs for quick lookup
        recent_map = {
            str(opp["opponent_id"]): {
                "match_count": opp["match_count"],
                "last_matched_at": opp["last_matched_at"]
            }
            for opp in recent_opponents
        }

        # Tier 2: Search all user profiles across all name fields (display_name, given_name, family_name)
        # This searches both Discord and Google users
        try:
            all_profiles = self.user_repo.search_users(query=query, limit=limit * 2)
        except Exception as e:
            # Database error or other issue, return empty results
            logger.error(f"Error searching user profiles for query '{query}': {e}", exc_info=True)
            return []

        # Merge and prioritize results
        results = []
        seen_ids = set()

        # First, add recent opponents that match the query
        for profile in all_profiles:
            user_id = str(profile["user_id"])

            # Skip current user (no self-reporting)
            if user_id == str(current_user_id):
                continue

            # Skip duplicates
            if user_id in seen_ids:
                continue

            # Skip users without valid numeric IDs (after stripping google_ prefix)
            try:
                numeric_id = str(self._normalize_user_id(user_id))
            except ValueError:
                logger.debug(f"Skipping user with invalid ID format: {user_id}")
                continue

            seen_ids.add(user_id)

            # Check if this is a recent opponent
            # Match by numeric ID (works for both Discord "123" and Google "google_123")
            if numeric_id in recent_map:
                recent_info = recent_map[numeric_id]
                results.append({
                    "user_id": user_id,
                    "display_name": profile["display_name"],
                    "avatar": profile.get("avatar"),
                    "recent_match_count": recent_info["match_count"],
                    "last_matched_at": recent_info["last_matched_at"],
                    "is_recent": True
                })
            else:
                results.append({
                    "user_id": user_id,
                    "display_name": profile["display_name"],
                    "avatar": profile.get("avatar"),
                    "recent_match_count": 0,
                    "last_matched_at": None,
                    "is_recent": False
                })

            # Stop when we have enough results
            if len(results) >= limit:
                break

        # Sort: recent opponents first (by last_matched_at DESC), then alphabetically
        def get_sort_key(x):
            # ISO datetime strings are lexicographically sortable
            # Use empty string for None to sort to the end
            timestamp_str = x["last_matched_at"] or ""
            return (
                not x["is_recent"],  # Recent first (False < True)
                timestamp_str,  # Older first (we'll reverse later)
                x["display_name"].lower()  # Then alphabetically
            )

        results.sort(key=get_sort_key, reverse=True)  # Reverse to get most recent first

        logger.info(
            f"Opponent search completed: user={current_user_id}, query='{query}', "
            f"found={len(results)} (recent={sum(1 for r in results if r['is_recent'])})"
        )

        return results[:limit]

    def _normalize_user_id(self, user_id: str) -> str:
        """
        Normalize user ID to numeric string format.

        Strips 'google_' prefix from Google OAuth users.
        Discord users are already numeric.
        Returns string to avoid overflow with large Google IDs.

        Args:
            user_id: User ID (numeric Discord ID or 'google_12345')

        Returns:
            str: Numeric user ID as string

        Raises:
            ValueError: If user_id cannot be converted to numeric format
        """
        user_id_str = str(user_id)

        # Strip 'google_' prefix if present
        if user_id_str.startswith("google_"):
            user_id_str = user_id_str[7:]  # Remove 'google_' (7 characters)

        # Validate numeric format but don't convert to int to avoid overflow
        try:
            int(user_id_str)  # Validation only
            return user_id_str  # Return as string
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f"Invalid user ID format: {user_id}")

    def _get_display_name_for_user(self, user_id: str) -> str:
        """
        Get display name for a user by checking both Discord and Google profiles.

        Args:
            user_id: Original user ID (numeric Discord ID or 'google_12345')

        Returns:
            str: Display name or fallback 'User {numeric_id}'
        """
        user_id_str = str(user_id)
        numeric_id = self._normalize_user_id(user_id_str)

        # Try Discord profile first (numeric ID)
        discord_profiles = self.user_repo.search_by_display_name(
            query=str(numeric_id), provider="discord", limit=1
        )
        if discord_profiles and discord_profiles[0]["user_id"] == str(numeric_id):
            return discord_profiles[0]["display_name"]

        # Try Google profile (google_ prefixed ID)
        google_user_id = f"google_{numeric_id}"
        google_profiles = self.user_repo.search_by_display_name(
            query=google_user_id, provider="google", limit=1
        )
        if google_profiles and google_profiles[0]["user_id"] == google_user_id:
            return google_profiles[0]["display_name"]

        # Fallback
        return f"User {numeric_id}"

    def create_match_report(
        self,
        submitter_id: str,
        opponent_id: str,
        result: str,
        went_first: str,
        submitter_deck_url: Optional[str] = None,
        opponent_deck_url: Optional[str] = None,
        final_life_submitter: int = 0,
        final_life_opponent: int = 0
    ) -> dict:
        """
        Create a new match report with validation and duplicate detection.

        Args:
            submitter_id: User ID of submitter (Discord ID or 'google_12345')
            opponent_id: User ID of opponent (Discord ID or 'google_12345')
            result: Match result ('won' or 'lost')
            went_first: Turn order ('submitter' or 'opponent')
            submitter_deck_url: Optional deck URL for submitter
            opponent_deck_url: Optional deck URL for opponent
            final_life_submitter: Submitter's final life total
            final_life_opponent: Opponent's final life total

        Returns:
            dict: {
                "success": True,
                "confirmation_id": int,
                "expires_at": int,
                "opponent": {"user_id": str, "display_name": str},
                "message": str
            }

        Raises:
            ValueError: If validation fails
            RuntimeError: If duplicate pending report or database error
        """
        # Step 0: Normalize user IDs (strip 'google_' prefix if present)
        try:
            submitter_numeric_id = self._normalize_user_id(submitter_id)
            opponent_numeric_id = self._normalize_user_id(opponent_id)
        except ValueError as e:
            raise ValueError(f"Invalid user ID: {e}")

        # Step 1: Validate all inputs
        validation = self.validate_match_report_input(
            submitter_id=str(submitter_numeric_id),
            opponent_id=str(opponent_numeric_id),
            result=result,
            went_first=went_first,
            submitter_deck_url=submitter_deck_url,
            opponent_deck_url=opponent_deck_url
        )

        if not validation["valid"]:
            error_details = ", ".join([
                f"{field}: {msg}" for field, msg in validation["errors"].items()
            ])
            raise ValueError(f"Validation failed: {error_details}")

        # Step 2: Check for duplicate pending reports (within 1 hour)
        has_duplicate = self.repo.check_duplicate_pending(
            submitter_id=submitter_numeric_id,
            opponent_id=opponent_numeric_id
        )

        if has_duplicate:
            raise RuntimeError(
                "You already have a pending match report with this opponent. "
                "Please wait for confirmation or expiration."
            )

        # Step 3: Calculate winner and loser IDs
        winner_loser = self.calculate_winner_loser(
            submitter_id=str(submitter_numeric_id),
            opponent_id=str(opponent_numeric_id),
            result=result
        )

        # Keep as strings to avoid overflow with large Google OAuth IDs
        winner_numeric_id = winner_loser["winner_id"]
        loser_numeric_id = winner_loser["loser_id"]

        # Step 4: Map deck URLs to winner/loser
        if result == "won":
            winner_deck_url = submitter_deck_url
            loser_deck_url = opponent_deck_url
            final_life_winner = final_life_submitter
            final_life_loser = final_life_opponent
        else:
            winner_deck_url = opponent_deck_url
            loser_deck_url = submitter_deck_url
            final_life_winner = final_life_opponent
            final_life_loser = final_life_submitter

        # Step 5: Create confirmation in database
        import time
        confirmation_id = self.repo.create_confirmation(
            submitter_id=submitter_numeric_id,
            opponent_id=opponent_numeric_id,
            winner_id=winner_numeric_id,
            loser_id=loser_numeric_id,
            final_life_winner=final_life_winner,
            final_life_loser=final_life_loser,
            went_first=went_first,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url
        )

        expires_at = int(time.time()) + (48 * 60 * 60)

        # Step 6: Get opponent display name for response
        # Try to get from user_profiles (check both Discord and Google)
        opponent_display_name = self._get_display_name_for_user(opponent_id)

        logger.info(
            f"Match report created: id={confirmation_id}, submitter={submitter_id} (normalized: {submitter_numeric_id}), "
            f"opponent={opponent_id} (normalized: {opponent_numeric_id}), result={result}, went_first={went_first}"
        )

        return {
            "success": True,
            "confirmation_id": confirmation_id,
            "expires_at": expires_at,
            "opponent": {
                "user_id": opponent_id,
                "display_name": opponent_display_name
            },
            "message": f"Match report submitted. Awaiting confirmation from {opponent_display_name}."
        }

    def confirm_match_report(
        self, confirmation_id: int, opponent_user_id: str, opponent_deck_url: Optional[str] = None
    ) -> dict:
        """
        Confirm a pending match report.

        This method:
        1. Verifies the confirmation exists and is pending
        2. Verifies the user is the opponent on the confirmation
        3. Saves the opponent's deck URL (if provided)
        4. Marks the confirmation as 'confirmed'
        5. Creates a match record in the database (TODO)
        6. Updates ELO ratings for both players (TODO)

        Args:
            confirmation_id: ID of confirmation to confirm
            opponent_user_id: Discord user ID of user confirming (must be the opponent)
            opponent_deck_url: Optional Curiosa.io deck URL for opponent's deck

        Returns:
            dict: {
                "success": True,
                "message": str,
                "match_id": int,
                "elo_changes": {
                    "winner": {"old": int, "new": int, "change": int},
                    "loser": {"old": int, "new": int, "change": int}
                }
            }

        Raises:
            ValueError: If confirmation not found or already processed
            PermissionError: If user is not the opponent on the confirmation
        """
        import time

        # Get confirmation
        confirmation = self.repo.get_confirmation_by_id(confirmation_id)

        if not confirmation:
            raise ValueError(f"Confirmation {confirmation_id} not found")

        # Check if confirmation is still pending
        if confirmation["status"] != "pending":
            raise ValueError(
                f"Confirmation {confirmation_id} is already {confirmation['status']}"
            )

        # Check if confirmation has expired
        if confirmation["expires_at"] < int(time.time()):
            raise ValueError(
                f"Confirmation {confirmation_id} has expired"
            )

        # Verify user is the opponent
        # Normalize both IDs for comparison (handles both Discord and Google users)
        opponent_numeric_id = self._normalize_user_id(opponent_user_id)
        if str(confirmation["opponent_discord_id"]) != str(opponent_numeric_id):
            raise PermissionError(
                "You are not authorized to confirm this match report"
            )

        # Update opponent's deck URL if provided
        if opponent_deck_url:
            # Validate deck URL format (strict: lowercase alphanumeric only)
            import re
            deck_url_pattern = r"^https://curiosa\.io/decks/[a-z0-9]+$"
            if not re.match(deck_url_pattern, opponent_deck_url):
                raise ValueError("Invalid Curiosa.io deck URL format. Expected: https://curiosa.io/decks/[deck-id] (lowercase letters and numbers only)")

            # Determine if opponent is winner or loser (use normalized ID for comparison)
            is_winner = str(confirmation["winner_discord_id"]) == str(opponent_numeric_id)
            deck_field = "winner_deck_url" if is_winner else "loser_deck_url"

            # Update the deck URL in the database
            conn = self.repo._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE match_confirmations SET {deck_field} = ? WHERE id = ?",
                (opponent_deck_url, confirmation_id)
            )
            conn.commit()
            conn.close()

            logger.info(
                f"Updated opponent deck URL: confirmation_id={confirmation_id}, "
                f"field={deck_field}, url={opponent_deck_url}"
            )

        # Get player IDs and display names FIRST (before any DB operations)
        from services.paper_elo import update_paper_elo
        from repositories.matches import MatchRepository
        from webapp_config import MATCH_RECORDS_DB_PATH
        import sqlite3

        winner_id = confirmation["winner_discord_id"]
        loser_id = confirmation["loser_discord_id"]

        # Get display names for logging
        winner_name = self._get_display_name_for_user(str(winner_id))
        loser_name = self._get_display_name_for_user(str(loser_id))

        # Get deck URLs from confirmation
        winner_deck_url = confirmation.get("winner_deck_url") or "No URL provided"
        loser_deck_url = confirmation.get("loser_deck_url") or "No URL provided"

        # Prepare JSON deck data (empty for web submissions - scraping requires bot dependencies)
        json_deck_data_winner = "{}"
        json_deck_data_loser = "{}"

        # Convert IDs to SQLite-safe format:
        # - Discord IDs (fit in 64-bit int): pass as int for correct matching
        # - Google OAuth IDs (exceed 64-bit int): pass as str to avoid OverflowError
        SQLITE_MAX_INT = 9223372036854775807

        def to_sqlite_id(val):
            try:
                int_val = int(val)
                if abs(int_val) <= SQLITE_MAX_INT:
                    return int_val
                return str(val)
            except (ValueError, TypeError):
                return str(val)

        reporter_id_safe = to_sqlite_id(confirmation["submitter_discord_id"])
        winner_id_safe = to_sqlite_id(winner_id)
        loser_id_safe = to_sqlite_id(loser_id)

        # CRITICAL: Perform all operations in correct order to maintain consistency
        # 1. Update ELO ratings
        # 2. Create match record
        # 3. Mark confirmation as confirmed (LAST - only if everything else succeeds)

        # Update winner's ELO (pass as strings to avoid OverflowError with large Google OAuth IDs)
        (
            winner_new_elo,
            winner_elo_change,
            winner_new_event_elo,
            winner_event_elo_change,
            event_active,
        ) = update_paper_elo(str(winner_id), winner_name, did_win=True, opponent_id=str(loser_id))

        # Update loser's ELO
        (
            loser_new_elo,
            loser_elo_change,
            loser_new_event_elo,
            loser_event_elo_change,
            _,
        ) = update_paper_elo(str(loser_id), loser_name, did_win=False, opponent_id=str(winner_id))

        # Create match record in match_records.db
        logger.info(f"Connecting to match_records database at: {MATCH_RECORDS_DB_PATH}")
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        # Verify table exists and log column info for debugging
        try:
            cur.execute("PRAGMA table_info(match_records)")
            columns = cur.fetchall()
            column_names = [col[1] for col in columns]
            logger.info(f"match_records table has {len(column_names)} columns: {', '.join(column_names)}")
        except Exception as e:
            logger.warning(f"Could not check match_records table schema: {e}")

        try:
            # Match bot's INSERT structure exactly
            cur.execute(
                """INSERT INTO match_records
                   (reporter_id, winner_id, winner_display_name, losser_id, losser_display_name,
                    did_win, timestamp, first_player, match_time, curiosa_url, curiosa_url_winner,
                    curiosa_url_loser, match_comment, json_deck_data, json_deck_data_winner,
                    json_deck_data_loser, winner_elo_change, loser_elo_change, winner_went_first,
                    loser_went_first, match_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    reporter_id_safe,  # reporter_id (int if fits, str if too large)
                    winner_id_safe,    # winner_id
                    winner_name,
                    loser_id_safe,     # losser_id
                    loser_name,
                    True,  # did_win (from winner's perspective)
                    datetime.datetime.now().isoformat(),
                    confirmation.get("went_first", "Unknown"),  # first_player
                    0,  # match_time (not tracked in confirmations yet)
                    winner_deck_url,  # curiosa_url (backward compatibility)
                    winner_deck_url,  # curiosa_url_winner
                    loser_deck_url,   # curiosa_url_loser
                    "Web-confirmed match",  # match_comment
                    json_deck_data_winner,  # json_deck_data (backward compatibility)
                    json_deck_data_winner,  # json_deck_data_winner
                    json_deck_data_loser,   # json_deck_data_loser
                    winner_event_elo_change if event_active else 0,  # winner_elo_change
                    loser_event_elo_change if event_active else 0,   # loser_elo_change
                    None,  # winner_went_first
                    None,  # loser_went_first
                    "ranked",  # match_type
                ),
            )

            match_id = cur.lastrowid
            conn.commit()

        except sqlite3.IntegrityError as e:
            conn.rollback()
            logger.error(
                f"Database integrity error creating match record:\n"
                f"  Error: {e}\n"
                f"  Reporter ID: {reporter_id_safe}\n"
                f"  Winner ID: {winner_id_safe} ({winner_name})\n"
                f"  Loser ID: {loser_id_safe} ({loser_name})\n"
                f"  Confirmation ID: {confirmation_id}",
                exc_info=True
            )
            raise RuntimeError(f"Failed to create match record: {e}")
        except sqlite3.OperationalError as e:
            conn.rollback()
            logger.error(
                f"Database operational error (missing column or table?):\n"
                f"  Error: {e}\n"
                f"  DB Path: {MATCH_RECORDS_DB_PATH}",
                exc_info=True
            )
            raise RuntimeError(f"Database error: {e}")
        finally:
            conn.close()

        # Mark confirmation as confirmed ONLY AFTER match record is created successfully
        self.repo.update_confirmation_status(
            confirmation_id=confirmation_id,
            status="confirmed",
            confirmed_at=int(time.time())
        )

        logger.info(
            f"Match confirmed: id={confirmation_id}, match_id={match_id}, "
            f"winner={winner_id} (+{winner_event_elo_change}), loser={loser_id} ({loser_event_elo_change})"
        )

        return {
            "success": True,
            "message": "Match confirmed successfully! ELO ratings have been updated.",
            "match_id": match_id,
            "elo_changes": {
                "winner": {
                    "old_elo": winner_new_elo - winner_elo_change,
                    "new_elo": winner_new_elo,
                    "change": winner_elo_change,
                    "event_change": winner_event_elo_change if event_active else 0,
                },
                "loser": {
                    "old_elo": loser_new_elo - loser_elo_change,
                    "new_elo": loser_new_elo,
                    "change": loser_elo_change,
                    "event_change": loser_event_elo_change if event_active else 0,
                },
            },
        }

    def deny_match_report(
        self, confirmation_id: int, opponent_user_id: str, reason: Optional[str] = None
    ) -> dict:
        """
        Deny/dispute a pending match report.

        This method:
        1. Verifies the confirmation exists and is pending
        2. Verifies the user is the opponent on the confirmation
        3. Marks the confirmation as 'disputed'
        4. Records the optional reason for dispute
        5. No match record is created, no ELO changes

        Args:
            confirmation_id: ID of confirmation to deny
            opponent_user_id: Discord user ID of user denying (must be the opponent)
            reason: Optional reason for dispute

        Returns:
            dict: {
                "success": True,
                "message": str
            }

        Raises:
            ValueError: If confirmation not found or already processed
            PermissionError: If user is not the opponent on the confirmation
        """
        import time

        # Get confirmation
        confirmation = self.repo.get_confirmation_by_id(confirmation_id)

        if not confirmation:
            raise ValueError(f"Confirmation {confirmation_id} not found")

        # Check if confirmation is still pending
        if confirmation["status"] != "pending":
            raise ValueError(
                f"Confirmation {confirmation_id} is already {confirmation['status']}"
            )

        # Check if confirmation has expired
        if confirmation["expires_at"] < int(time.time()):
            raise ValueError(
                f"Confirmation {confirmation_id} has expired"
            )

        # Verify user is the opponent
        # Normalize both IDs for comparison (handles both Discord and Google users)
        opponent_numeric_id = self._normalize_user_id(opponent_user_id)
        if str(confirmation["opponent_discord_id"]) != str(opponent_numeric_id):
            raise PermissionError(
                "You are not authorized to deny this match report"
            )

        # Mark confirmation as disputed
        self.repo.update_confirmation_status(
            confirmation_id=confirmation_id,
            status="disputed",
            confirmed_at=int(time.time()),
            dispute_reason=reason
        )

        logger.info(
            f"Match denied: id={confirmation_id}, reason={reason}"
        )

        return {
            "success": True,
            "message": "Match report denied. No changes have been made to ratings."
        }
