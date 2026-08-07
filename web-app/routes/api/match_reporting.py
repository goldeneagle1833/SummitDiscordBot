"""API routes for web-based match reporting."""

import logging
import sqlite3
from flask import Blueprint, jsonify, request, session

from services.match_confirmation import MatchConfirmationService
from repositories.user_profiles import UserProfileRepository
from repositories.match_confirmation import MatchConfirmationRepository
from webapp_config import MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)

# Create blueprint for match reporting API
match_reporting_bp = Blueprint("match_reporting", __name__)


@match_reporting_bp.route("/search-opponents", methods=["GET"])
def search_opponents():
    """
    GET /api/match-report/search-opponents

    Search for opponents by display name (autocomplete).

    Query Parameters:
        q (str): Search query (min 2 characters recommended)
        limit (int): Max results to return (default 10, max 50)

    Returns:
        JSON: {"success": bool, "opponents": [...]}

    Example:
        GET /api/match-report/search-opponents?q=Player&limit=5
    """
    # Check authentication
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication required. Please log in."
            }
        }), 401

    # Get query parameters
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 10, type=int)

    # Validate query parameter
    if not query:
        return jsonify({
            "success": False,
            "error": {
                "code": "MISSING_QUERY",
                "message": "Query parameter 'q' is required"
            }
        }), 400

    if len(query) < 2:
        return jsonify({
            "success": False,
            "error": {
                "code": "QUERY_TOO_SHORT",
                "message": "Query must be at least 2 characters"
            }
        }), 400

    # Limit bounds check
    if limit > 50:
        limit = 50

    try:
        current_user_id = session["user_id"]
        service = MatchConfirmationService()

        # Call service layer to search opponents
        opponents = service.search_opponents(current_user_id, query, limit)

        logger.info(f"Opponent search: user={current_user_id}, query='{query}', found={len(opponents)}")

        return jsonify({
            "success": True,
            "opponents": opponents
        })

    except ValueError as e:
        # Invalid user ID format
        logger.warning(f"Invalid user ID in opponent search: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_USER_ID",
                "message": "Your user profile could not be validated. Please try logging out and back in."
            }
        }), 400

    except OverflowError as e:
        # Integer overflow (should not happen after fixes, but just in case)
        logger.warning(f"Integer overflow in opponent search: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "ID_OVERFLOW",
                "message": "User ID format error. Please try logging out and back in."
            }
        }), 400

    except Exception as e:
        # Catch-all for unexpected errors
        error_type = type(e).__name__
        logger.error(f"Unexpected error searching opponents ({error_type}): {e}", exc_info=True)

        # Provide different messages for database vs other errors
        if "database" in str(e).lower() or "sqlite" in str(e).lower():
            error_code = "DATABASE_ERROR"
            error_msg = "Database connection error. Please try again in a moment."
        else:
            error_code = "SEARCH_ERROR"
            error_msg = f"Search failed ({error_type}). Please try again or contact support."

        return jsonify({
            "success": False,
            "error": {
                "code": error_code,
                "message": error_msg
            }
        }), 500


@match_reporting_bp.route("/submit", methods=["POST"])
def submit_match_report():
    """
    POST /api/match-report/submit

    Submit a new match report with pending confirmation status.

    Request Body (JSON):
        {
            "opponent_user_id": str,
            "result": "won" | "lost",
            "went_first": "submitter" | "opponent",
            "submitter_deck_url": str (optional),
            "opponent_deck_url": str (optional),
            "final_life_submitter": int,
            "final_life_opponent": int
        }

    Returns:
        JSON: {"success": bool, "confirmation_id": int, "expires_at": int, ...}

    Status Codes:
        201: Created successfully
        400: Validation error
        401: Not authenticated
        409: Duplicate pending report
        500: Server error
    """
    # Check authentication
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication required. Please log in."
            }
        }), 401

    # Get request data
    data = request.get_json()
    if not data:
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_JSON",
                "message": "Request body must be valid JSON"
            }
        }), 400

    # Extract fields
    submitter_id = session["user_id"]
    opponent_id = data.get("opponent_user_id")
    result = data.get("result")
    went_first = data.get("went_first")
    submitter_deck_url = data.get("submitter_deck_url")
    submitter_avatar = data.get("submitter_avatar")
    final_life_submitter = data.get("final_life_submitter")
    final_life_opponent = data.get("final_life_opponent")
    match_type = data.get("match_type", "ranked")  # Default to ranked if not provided
    season_id = data.get("season_id")  # Optional season to count match toward
    match_comment = data.get("match_comment", "")  # Optional match notes

    try:
        service = MatchConfirmationService()

        # Call service layer to create match report
        # Note: opponent_deck_url will be provided by opponent on confirmation
        result_data = service.create_match_report(
            submitter_id=submitter_id,
            opponent_id=opponent_id,
            result=result,
            went_first=went_first,
            submitter_deck_url=submitter_deck_url,
            opponent_deck_url=None,  # Opponent provides their deck URL on confirmation
            submitter_avatar=submitter_avatar,
            opponent_avatar=None,
            final_life_submitter=final_life_submitter,
            final_life_opponent=final_life_opponent,
            match_type=match_type,
            season_id=season_id,
            match_comment=match_comment,
        )

        logger.info(
            f"Match report submitted: id={result_data['confirmation_id']}, "
            f"submitter={submitter_id}, opponent={opponent_id}, result={result}"
        )

        return jsonify(result_data), 201

    except ValueError as e:
        # Validation errors
        logger.warning(f"Validation error in match report: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(e)
            }
        }), 400

    except RuntimeError as e:
        # Duplicate or other business logic errors
        error_msg = str(e)
        if "duplicate" in error_msg.lower():
            code = "DUPLICATE_PENDING"
            status = 409
        else:
            code = "BUSINESS_ERROR"
            status = 400

        logger.warning(f"Business logic error: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": code,
                "message": error_msg
            }
        }), status

    except OverflowError as e:
        # Integer overflow (should not happen after fixes, but just in case)
        logger.warning(f"Integer overflow in match report: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "ID_OVERFLOW",
                "message": "User ID format error. Please try logging out and back in."
            }
        }), 400

    except Exception as e:
        # Unexpected errors
        error_type = type(e).__name__
        logger.error(f"Unexpected error creating match report ({error_type}): {e}", exc_info=True)

        # Provide different messages for database vs other errors
        if "database" in str(e).lower() or "sqlite" in str(e).lower():
            error_code = "DATABASE_ERROR"
            error_msg = "Database connection error. Please try again in a moment."
        else:
            error_code = "SERVER_ERROR"
            error_msg = f"Failed to create match report ({error_type}). Please try again or contact support."

        return jsonify({
            "success": False,
            "error": {
                "code": error_code,
                "message": error_msg
            }
        }), 500


@match_reporting_bp.route("/pending", methods=["GET"])
def get_pending_confirmations():
    """
    GET /api/match-report/pending

    Get all pending match confirmations for the current user.

    Returns:
        JSON: {"success": bool, "pending_confirmations": [...], "count": int}
    """
    # Check authentication
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication required"
            }
        }), 401

    try:
        current_user_id = session["user_id"]
        service = MatchConfirmationService()
        confirmation_repo = MatchConfirmationRepository()
        user_profile_repo = UserProfileRepository()

        # Get pending confirmations where user is the opponent
        # IDs are stored as-is (with google_ prefix for Google users), so search with original ID
        current_user_id_str = str(current_user_id)
        confirmations = confirmation_repo.get_pending_confirmations(current_user_id_str)

        # Also search with normalized ID in case of mixed storage
        if current_user_id_str.startswith("google_"):
            numeric_id = current_user_id_str[7:]
            confirmations += confirmation_repo.get_pending_confirmations(numeric_id)
        else:
            confirmations += confirmation_repo.get_pending_confirmations(f"google_{current_user_id_str}")

        # Deduplicate by confirmation ID
        seen_ids = set()
        unique_confirmations = []
        for c in confirmations:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                unique_confirmations.append(c)
        confirmations = unique_confirmations

        # Enrich with submitter display names
        enriched_confirmations = []
        for confirmation in confirmations:
            # Get submitter display name (handles both Discord and Google users)
            # submitter_discord_id may have google_ prefix for Google users
            submitter_id_str = str(confirmation["submitter_discord_id"])

            # Use the service's display name resolver which handles all ID formats
            submitter_display_name = service._get_display_name_for_user(submitter_id_str)
            submitter_avatar = None

            # Try to get avatar from profile
            profile = user_profile_repo.get_by_user_id(submitter_id_str)
            if profile:
                submitter_avatar = profile.get("avatar")

            # Add submitter info to confirmation
            confirmation["submitter_display_name"] = submitter_display_name
            confirmation["submitter_avatar"] = submitter_avatar
            submitter_is_winner = (
                str(confirmation["submitter_discord_id"])
                == str(confirmation["winner_discord_id"])
            )
            confirmation["reported_match_avatar"] = confirmation.get(
                "winner_avatar" if submitter_is_winner else "loser_avatar"
            )

            # Remove deck URLs from confirmation response - they should not be visible until after confirmation
            confirmation.pop("winner_deck_url", None)
            confirmation.pop("loser_deck_url", None)

            enriched_confirmations.append(confirmation)

        logger.info(f"Fetched pending confirmations: user={current_user_id}, count={len(enriched_confirmations)}")

        return jsonify({
            "success": True,
            "pending_confirmations": enriched_confirmations,
            "count": len(enriched_confirmations)
        })

    except Exception as e:
        logger.error(f"Error fetching pending confirmations: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "FETCH_ERROR",
                "message": "Failed to fetch pending confirmations"
            }
        }), 500


@match_reporting_bp.route("/confirm/<int:confirmation_id>", methods=["POST"])
def confirm_match_report(confirmation_id):
    """
    POST /api/match-report/confirm/<confirmation_id>

    Confirm a pending match report.

    Path Parameters:
        confirmation_id (int): ID of confirmation to confirm

    Request Body (JSON, optional):
        {
            "deck_url": str (optional Curiosa.io deck URL)
        }

    Returns:
        JSON: {"success": bool, "message": str, "match_id": int (optional)}

    Status Codes:
        200: Confirmed successfully
        401: Not authenticated
        403: Not authorized (not the opponent)
        404: Confirmation not found or expired
        500: Server error
    """
    # Check authentication
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication required"
            }
        }), 401

    # Get optional deck URL and comment from request body
    data = request.get_json() or {}
    deck_url = data.get("deck_url")
    avatar = data.get("avatar")
    confirmer_comment = data.get("match_comment", "")

    try:
        current_user_id = session["user_id"]
        service = MatchConfirmationService()

        # Confirm the match report
        result = service.confirm_match_report(
            confirmation_id,
            current_user_id,
            deck_url,
            opponent_avatar=avatar,
            confirmer_comment=confirmer_comment,
        )

        logger.info(
            f"Match confirmed: confirmation_id={confirmation_id}, "
            f"opponent={current_user_id}, match_id={result.get('match_id')}"
        )

        return jsonify(result), 200

    except ValueError as e:
        # Not found or expired
        logger.warning(f"Confirmation not found: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": str(e)
            }
        }), 404

    except PermissionError as e:
        # Not authorized (not the opponent)
        logger.warning(f"Unauthorized confirmation attempt: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "FORBIDDEN",
                "message": str(e)
            }
        }), 403

    except Exception as e:
        # Unexpected errors
        error_type = type(e).__name__
        logger.error(f"Unexpected error confirming match ({error_type}): {e}", exc_info=True)

        # Provide different messages for database vs other errors
        if "database" in str(e).lower() or "sqlite" in str(e).lower():
            error_code = "DATABASE_ERROR"
            error_msg = "Database connection error. Please try again in a moment."
        else:
            error_code = "CONFIRMATION_ERROR"
            error_msg = f"Failed to confirm match ({error_type}). Please try again or contact support."

        return jsonify({
            "success": False,
            "error": {
                "code": error_code,
                "message": error_msg
            }
        }), 500


@match_reporting_bp.route("/deny/<int:confirmation_id>", methods=["POST"])
def deny_match_report(confirmation_id):
    """
    POST /api/match-report/deny/<confirmation_id>

    Deny/dispute a pending match report.

    Path Parameters:
        confirmation_id (int): ID of confirmation to deny

    Request Body (JSON, optional):
        {
            "reason": str (optional dispute reason)
        }

    Returns:
        JSON: {"success": bool, "message": str}

    Status Codes:
        200: Denied successfully
        401: Not authenticated
        403: Not authorized (not the opponent)
        404: Confirmation not found or expired
        500: Server error
    """
    # Check authentication
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication required"
            }
        }), 401

    # Get optional reason from request body
    data = request.get_json() or {}
    reason = data.get("reason")

    try:
        current_user_id = session["user_id"]
        service = MatchConfirmationService()

        # Deny the match report
        result = service.deny_match_report(confirmation_id, current_user_id, reason)

        logger.info(
            f"Match denied: confirmation_id={confirmation_id}, "
            f"opponent={current_user_id}, reason={reason}"
        )

        return jsonify(result), 200

    except ValueError as e:
        # Not found or expired
        logger.warning(f"Confirmation not found: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": str(e)
            }
        }), 404

    except PermissionError as e:
        # Not authorized (not the opponent)
        logger.warning(f"Unauthorized denial attempt: {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "FORBIDDEN",
                "message": str(e)
            }
        }), 403

    except Exception as e:
        # Unexpected errors
        error_type = type(e).__name__
        logger.error(f"Unexpected error denying match ({error_type}): {e}", exc_info=True)

        # Provide different messages for database vs other errors
        if "database" in str(e).lower() or "sqlite" in str(e).lower():
            error_code = "DATABASE_ERROR"
            error_msg = "Database connection error. Please try again in a moment."
        else:
            error_code = "DENIAL_ERROR"
            error_msg = f"Failed to deny match ({error_type}). Please try again or contact support."

        return jsonify({
            "success": False,
            "error": {
                "code": error_code,
                "message": error_msg
            }
        }), 500


@match_reporting_bp.route("/edit-comment", methods=["POST"])
def edit_match_comment():
    """Edit the logged-in user's match comment/note.

    Request Body (JSON):
        match_id (int): ID of the match
        match_source (str): 'web' or 'bot'
        new_comment (str): New comment text (max 500 chars, empty to clear)
    """
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json() or {}
    match_id = data.get("match_id")
    match_source = data.get("match_source")
    new_comment = (data.get("new_comment") or "").strip()

    if not match_id or match_source not in ("web", "bot"):
        return jsonify({"success": False, "error": "match_id and match_source (web/bot) required"}), 400

    if len(new_comment) > 500:
        return jsonify({"success": False, "error": "Comment must be 500 characters or fewer"}), 400

    current_user_id = str(session["user_id"])
    auth_provider = session.get("auth_provider", "discord")

    try:
        # Both bot and web matches live in match_records.db
        db_path = str(MATCH_RECORDS_DB_PATH)
        if match_source == "web":
            table = "match_reports_web"
            id_col = "match_id"
            # Web matches store user IDs with provider prefix
            user_id_for_query = f"google_{current_user_id}" if auth_provider == "google" else current_user_id
        else:
            # Bot matches use numeric IDs
            user_id_for_query = current_user_id
            if user_id_for_query.startswith("google_"):
                user_id_for_query = user_id_for_query[7:]
            # Archived bot matches have match_id >= 1_000_000_000
            # (player page returns rowid + 1000000000 for match_records_archive)
            try:
                numeric_match_id = int(match_id)
            except (ValueError, TypeError):
                numeric_match_id = 0
            if numeric_match_id >= 1_000_000_000:
                table = "match_records_archive"
                id_col = "rowid"
                match_id = numeric_match_id - 1_000_000_000
            else:
                table = "match_records"
                id_col = "rowid"

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Verify the table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cur.fetchone():
            conn.close()
            return jsonify({"success": False, "error": f"Match table not found in database"}), 404

        # Fetch the existing match - use column-safe query for bot matches
        # which may have varying schemas
        try:
            cur.execute(
                f"SELECT winner_id, losser_id, match_comment, reporter_id FROM {table} WHERE {id_col} = ?",
                (match_id,),
            )
        except sqlite3.OperationalError:
            # Fallback: match_comment or reporter_id column may not exist
            try:
                cur.execute(
                    f"SELECT winner_id, losser_id, NULL, NULL FROM {table} WHERE {id_col} = ?",
                    (match_id,),
                )
            except sqlite3.OperationalError as e2:
                conn.close()
                return jsonify({"success": False, "error": f"Database schema error: {e2}"}), 500

        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": "Match not found"}), 404

        winner_id, loser_id, old_comment, reporter_id = row

        # Verify user is a participant
        if str(winner_id) != str(user_id_for_query) and str(loser_id) != str(user_id_for_query):
            conn.close()
            return jsonify({"success": False, "error": "Not authorized to edit this match"}), 403

        # Determine if user is reporter or confirmer
        is_reporter = reporter_id is not None and str(reporter_id) == str(user_id_for_query)
        old_comment = old_comment or ""

        # Parse existing merged comment to extract the other user's portion
        other_part = ""
        if " | Opponent: " in old_comment:
            reporter_part, confirmer_part = old_comment.split(" | Opponent: ", 1)
            other_part = confirmer_part if is_reporter else reporter_part
        elif old_comment.startswith("Opponent: "):
            if not is_reporter:
                other_part = ""  # confirmer's comment only, no reporter part
            else:
                other_part = old_comment[len("Opponent: "):]
        elif old_comment in ("Web-confirmed match", ""):
            other_part = ""
        else:
            # Only reporter's comment exists
            if not is_reporter:
                other_part = old_comment

        # Rebuild the merged comment
        if is_reporter:
            reporter_text = new_comment
            confirmer_text = other_part
        else:
            reporter_text = other_part
            confirmer_text = new_comment

        if reporter_text and confirmer_text:
            merged = f"{reporter_text} | Opponent: {confirmer_text}"
        elif reporter_text:
            merged = reporter_text
        elif confirmer_text:
            merged = f"Opponent: {confirmer_text}"
        else:
            merged = ""

        # Try updating match_comment; add the column if it doesn't exist
        try:
            cur.execute(
                f"UPDATE {table} SET match_comment = ? WHERE {id_col} = ?",
                (merged, match_id),
            )
        except sqlite3.OperationalError:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN match_comment TEXT")
            cur.execute(
                f"UPDATE {table} SET match_comment = ? WHERE {id_col} = ?",
                (merged, match_id),
            )
        conn.commit()
        conn.close()

        return jsonify({"success": True, "comment": new_comment})

    except Exception as e:
        logger.error(
            f"Error editing match comment for match_id={match_id}, source={match_source}, "
            f"user={current_user_id}, db={db_path}, table={table}: {e}",
            exc_info=True,
        )
        return jsonify({"success": False, "error": f"Failed to update comment: {e}"}), 500
