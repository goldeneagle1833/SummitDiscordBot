"""API routes for web-based match reporting."""

import logging
from flask import Blueprint, jsonify, request, session

from services.match_confirmation import MatchConfirmationService
from repositories.user_profiles import UserProfileRepository
from repositories.match_confirmation import MatchConfirmationRepository

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
        logger.error(f"Integer overflow in opponent search: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "ID_OVERFLOW",
                "message": "User ID format error. Please contact support if this persists."
            }
        }), 500

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
    final_life_submitter = data.get("final_life_submitter")
    final_life_opponent = data.get("final_life_opponent")

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
            final_life_submitter=final_life_submitter,
            final_life_opponent=final_life_opponent
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
        logger.error(f"Integer overflow in match report: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "ID_OVERFLOW",
                "message": "User ID format error. Please contact support if this persists."
            }
        }), 500

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

        # Normalize user ID (strip 'google_' prefix if present)
        current_numeric_id = service._normalize_user_id(current_user_id)

        # Get pending confirmations where user is the opponent
        confirmations = confirmation_repo.get_pending_confirmations(current_numeric_id)

        # Enrich with submitter display names
        enriched_confirmations = []
        for confirmation in confirmations:
            # Get submitter display name (handles both Discord and Google users)
            # The submitter_discord_id is numeric, but could be from Discord or Google user
            submitter_numeric_id = confirmation["submitter_discord_id"]

            # Try to find profile by checking both Discord and Google
            submitter_display_name = "Unknown Player"
            submitter_avatar = None

            # Try Discord first
            discord_profiles = user_profile_repo.search_by_display_name(
                query=str(submitter_numeric_id), provider="discord", limit=1
            )
            if discord_profiles and discord_profiles[0]["user_id"] == str(submitter_numeric_id):
                submitter_display_name = discord_profiles[0]["display_name"]
                submitter_avatar = discord_profiles[0].get("avatar")
            else:
                # Try Google
                google_user_id = f"google_{submitter_numeric_id}"
                google_profiles = user_profile_repo.search_by_display_name(
                    query=google_user_id, provider="google", limit=1
                )
                if google_profiles and google_profiles[0]["user_id"] == google_user_id:
                    submitter_display_name = google_profiles[0]["display_name"]
                    submitter_avatar = google_profiles[0].get("avatar")

            # Add submitter info to confirmation
            confirmation["submitter_display_name"] = submitter_display_name
            confirmation["submitter_avatar"] = submitter_avatar

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

    # Get optional deck URL from request body
    data = request.get_json() or {}
    deck_url = data.get("deck_url")

    try:
        current_user_id = session["user_id"]
        service = MatchConfirmationService()

        # Confirm the match report
        result = service.confirm_match_report(confirmation_id, current_user_id, deck_url)

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
        logger.error(f"Error confirming match: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "SERVER_ERROR",
                "message": "Failed to confirm match. Please try again."
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
        logger.error(f"Error denying match: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "SERVER_ERROR",
                "message": "Failed to deny match. Please try again."
            }
        }), 500
