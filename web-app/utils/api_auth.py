"""API key authentication for external service integrations."""

from functools import wraps

from flask import jsonify, request

import webapp_config


def require_api_key(f):
    """Decorator that validates the X-API-Key header against the configured RealmsDraft key."""

    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != webapp_config.REALMSDRAFT_API_KEY:
            return jsonify({"success": False, "error": "Invalid API key"}), 401
        return f(*args, **kwargs)

    return decorated
