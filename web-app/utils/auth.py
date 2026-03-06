"""Authentication and authorization utilities."""

import logging
from functools import wraps
from flask import request, session, jsonify

from webapp_config import VALID_API_KEYS, ADMINS

logger = logging.getLogger(__name__)


def require_api_key(f):
    """Decorator to require API key authentication for endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        provided_key = request.headers.get("X-API-Key") or request.headers.get(
            "Authorization"
        )

        if provided_key and provided_key.startswith("Bearer "):
            provided_key = provided_key[7:]

        if not VALID_API_KEYS:
            logger.error("No API keys configured in environment")
            return jsonify({"error": "API authentication not configured"}), 500

        if not provided_key or provided_key not in VALID_API_KEYS:
            logger.warning(
                f"Unauthorized API access attempt from {request.remote_addr}"
            )
            return jsonify({"error": "Invalid or missing API key"}), 401

        return f(*args, **kwargs)

    return decorated_function


def require_auth(f):
    """Decorator requiring either session login OR valid API key.

    Use this for endpoints that should be accessible from:
    - Browser users who are logged in (session)
    - Server-to-server calls (API key)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session first
        if session.get("user_id"):
            return f(*args, **kwargs)

        # Check API key
        provided_key = request.headers.get("X-API-Key") or request.headers.get(
            "Authorization"
        )
        if provided_key and provided_key.startswith("Bearer "):
            provided_key = provided_key[7:]

        if provided_key and provided_key in VALID_API_KEYS:
            return f(*args, **kwargs)

        logger.warning(
            f"Unauthorized access attempt to {request.path} from {request.remote_addr}"
        )
        return jsonify({"error": "Authentication required (login or API key)"}), 401

    return decorated_function


def is_admin() -> bool:
    """Check if the current user is an admin.

    Access granted if:
    - Request is from localhost
    - User is in ADMINS list (session auth)
    - Request has valid API key
    """
    # Localhost has full admin access
    remote_addr = request.remote_addr or ""
    host = request.host or ""
    if remote_addr in ("127.0.0.1", "::1", "localhost") or host.startswith("localhost") or host.startswith("127.0.0.1"):
        return True

    # API key grants access
    provided_key = request.headers.get("X-API-Key") or request.headers.get(
        "Authorization"
    )
    if provided_key and provided_key.startswith("Bearer "):
        provided_key = provided_key[7:]
    if provided_key and provided_key in VALID_API_KEYS:
        return True

    # Check session user against admin list
    user_id = session.get("user_id")
    if user_id is None:
        return False
    return int(user_id) in ADMINS or str(user_id) in [
        str(x) for x in ADMINS
    ]


def require_admin(f):
    """Decorator requiring admin access (session admin, localhost, or API key)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            logger.warning(
                f"Non-admin access attempt to {request.path} from {request.remote_addr}"
            )
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_current_user() -> dict | None:
    """Get the currently logged in user from session, or None."""
    if "user_id" in session:
        return {
            "id": session["user_id"],
            "username": session.get("username"),
            "avatar": session.get("avatar"),
        }
    return None
