"""Authentication and authorization utilities."""

import logging
from functools import wraps
from flask import request, session, jsonify

from webapp_config import VALID_API_KEYS, ADMINS, CURIO_EDITORS

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

    decorated_function._auth_required = True
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

    decorated_function._auth_required = True
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

    # Convert user_id to string for comparison (handles both Discord IDs and Google IDs)
    user_id_str = str(user_id)

    # Check if user_id matches any admin ID (as string)
    for admin_id in ADMINS:
        if user_id_str == str(admin_id):
            return True

    return False


def is_curio_editor() -> bool:
    """Check if the current user can edit curio entries.

    Access granted if:
    - User is an admin (full access)
    - User is in CURIO_EDITORS list
    """
    if is_admin():
        return True

    user_id = session.get("user_id")
    if user_id is None:
        return False

    user_id_str = str(user_id)
    for editor_id in CURIO_EDITORS:
        if user_id_str == str(editor_id):
            return True

    return False


def is_creator() -> bool:
    """Check if the current user has the creator role.

    Access granted if:
    - User is an admin (superset)
    - User has the creator role from Discord
    - User has been manually granted access via the admin panel (creator_access table)
    """
    if is_admin():
        return True

    if session.get("is_creator"):
        return True

    user_id = session.get("user_id")
    if user_id:
        try:
            from repositories.creator_access import CreatorAccessRepository
            repo = CreatorAccessRepository()
            if repo.has_access(str(user_id)):
                return True
        except Exception:
            pass

    return False


def require_creator(f):
    """Decorator requiring creator role (Discord role, admin, or API key)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_creator():
            logger.warning(
                f"Non-creator access attempt to {request.path} from {request.remote_addr}"
            )
            return jsonify({"error": "Creator access required"}), 403
        return f(*args, **kwargs)
    decorated_function._auth_required = True
    return decorated_function


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
    decorated_function._auth_required = True
    return decorated_function


def is_explorer_admin() -> bool:
    """Check if the current user can manage Explorer Standings events/seasons.

    Access granted if:
    - User is a global admin (superset)
    - User's Discord ID is in the explorer_admins table
    """
    if is_admin():
        return True

    user_id = session.get("user_id")
    if user_id:
        try:
            from repositories.explorer import ExplorerRepository
            repo = ExplorerRepository()
            if repo.is_explorer_admin(str(user_id)):
                return True
        except Exception:
            pass

    return False


def require_explorer_admin(f):
    """Decorator requiring Explorer admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_explorer_admin():
            logger.warning(
                f"Non-explorer-admin access attempt to {request.path} from {request.remote_addr}"
            )
            return jsonify({"error": "Explorer admin access required"}), 403
        return f(*args, **kwargs)
    decorated_function._auth_required = True
    return decorated_function


def is_rumble_admin() -> bool:
    """Check if the current user can manage Rumble bones/prizes.

    Access granted if:
    - User is a global admin (superset)
    - User's Discord ID is in the rumble_admins table
    """
    if is_admin():
        return True

    user_id = session.get("user_id")
    if user_id:
        try:
            from repositories.rumble_repo import RumbleRepository
            repo = RumbleRepository()
            if repo.is_rumble_admin(str(user_id)):
                return True
        except Exception:
            pass

    return False


def require_rumble_admin(f):
    """Decorator requiring Rumble admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_rumble_admin():
            logger.warning(
                f"Non-rumble-admin access attempt to {request.path} from {request.remote_addr}"
            )
            return jsonify({"error": "Rumble admin access required"}), 403
        return f(*args, **kwargs)
    decorated_function._auth_required = True
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
