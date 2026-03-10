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

    except Exception as e:
        logger.error(f"Error searching opponents: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "SEARCH_ERROR",
                "message": "Failed to search opponents. Please try again."
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
    opponent_deck_url = data.get("opponent_deck_url")
    final_life_submitter = data.get("final_life_submitter")
    final_life_opponent = data.get("final_life_opponent")

    try:
        service = MatchConfirmationService()

        # Call service layer to create match report
        result_data = service.create_match_report(
            submitter_id=submitter_id,
            opponent_id=opponent_id,
            result=result,
            went_first=went_first,
            submitter_deck_url=submitter_deck_url,
            opponent_deck_url=opponent_deck_url,
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

    except Exception as e:
        # Unexpected errors
        logger.error(f"Error creating match report: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "DATABASE_ERROR",
                "message": "Failed to create match report. Please try again."
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
        repo = MatchConfirmationRepository()

        # Get pending confirmations where user is the opponent
        confirmations = repo.get_pending_confirmations(current_user_id)

        # TODO: Enrich with submitter display names (Phase 4)

        logger.info(f"Fetched pending confirmations: user={current_user_id}, count={len(confirmations)}")

        return jsonify({
            "success": True,
            "pending_confirmations": confirmations,
            "count": len(confirmations)
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
