"""Store-admin permission tier.

Deliberately does NOT inherit from the global ADMINS list: only Discord IDs
listed in the STORE_ADMIN_IDS environment variable may manage products,
view/ship orders, or download store database backups.

API-key access is still honored for server-side maintenance scripts.
"""

import logging
import os
from functools import wraps

from flask import jsonify, request, session

from utils.auth import _api_key_valid, _extract_api_key

logger = logging.getLogger(__name__)

STORE_ADMIN_IDS = [
    i.strip() for i in os.environ.get("STORE_ADMIN_IDS", "").split(",") if i.strip()
]


def is_store_admin() -> bool:
    """Check if the current user may access the store admin section.

    Access granted if:
    - Request has a valid API key
    - Session user's ID is in STORE_ADMIN_IDS

    NOTE: global admins (ADMINS) are intentionally NOT included.

    NOTE: there is no localhost shortcut. `request.host` comes from the
    client's Host header (proxied through nginx), so `Host: localhost` would
    grant store admin to anyone, and behind the gunicorn unix socket
    `remote_addr` is not a meaningful client IP. See utils.auth.is_admin.
    """
    if _api_key_valid(_extract_api_key()):
        return True

    user_id = session.get("user_id")
    if user_id is None:
        return False
    return str(user_id) in STORE_ADMIN_IDS


def require_store_admin(f):
    """Decorator requiring store-admin access."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_store_admin():
            logger.warning(
                f"Non-store-admin access attempt to {request.path} "
                f"from {request.remote_addr}"
            )
            return jsonify({"error": "Store admin access required"}), 403
        return f(*args, **kwargs)

    decorated_function._auth_required = True
    return decorated_function
