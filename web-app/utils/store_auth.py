"""Store-admin permission tier.

Deliberately does NOT inherit from the global ADMINS list: only Discord IDs
listed in the STORE_ADMIN_IDS environment variable may manage products,
view/ship orders, or download store database backups.

Localhost and API-key access are still honored to match the dev workflow
used by the rest of the admin routes.
"""

import logging
import os
from functools import wraps

from flask import jsonify, request, session

from webapp_config import VALID_API_KEYS

logger = logging.getLogger(__name__)

STORE_ADMIN_IDS = [
    i.strip() for i in os.environ.get("STORE_ADMIN_IDS", "").split(",") if i.strip()
]


def is_store_admin() -> bool:
    """Check if the current user may access the store admin section.

    Access granted if:
    - Request is from localhost (dev workflow)
    - Request has a valid API key
    - Session user's ID is in STORE_ADMIN_IDS

    NOTE: global admins (ADMINS) are intentionally NOT included.
    """
    remote_addr = request.remote_addr or ""
    host = request.host or ""
    if (
        remote_addr in ("127.0.0.1", "::1", "localhost")
        or host.startswith("localhost")
        or host.startswith("127.0.0.1")
    ):
        return True

    provided_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
    if provided_key and provided_key.startswith("Bearer "):
        provided_key = provided_key[7:]
    if provided_key and provided_key in VALID_API_KEYS:
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
