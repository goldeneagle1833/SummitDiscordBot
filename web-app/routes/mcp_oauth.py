"""Sign-in pages and endpoints for AI apps (see services/mcp_oauth.py).

/.well-known/oauth-authorization-server   where everything is (RFC 8414)
/auth/mcp/register                         an app registers itself (RFC 7591)
/auth/mcp/authorize                        sign in (site /login) + "Allow this app?" screen
/auth/mcp/token                            code / refresh token -> access token
/auth/mcp/revoke                           an app signs out (RFC 7009)
"""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, parse_qsl

from flask import Blueprint, jsonify, redirect, render_template_string, request, session

from services import mcp_oauth
from services.ranked_analytics import claim_request

logger = logging.getLogger(__name__)

ISSUER = os.environ.get("MCP_OAUTH_ISSUER", "https://sorcererssummit.com").rstrip("/")

mcp_oauth_bp = Blueprint("mcp_oauth", __name__)
mcp_wellknown_bp = Blueprint("mcp_wellknown", __name__)


def _client_ip() -> str:
    return (request.headers.get("CF-Connecting-IP")
            or (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            or request.remote_addr or "unknown")


def _limited(kind: str) -> bool:
    return not claim_request(f"mcp-oauth-{kind}:{_client_ip()}")


def _oauth_error(err: mcp_oauth.OAuthError):
    response = jsonify(err.body())
    response.status_code = err.status
    response.headers["Cache-Control"] = "no-store"
    return response


def _cors(response):
    # AI apps call these from their own servers or browsers
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, mcp-protocol-version"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def metadata() -> dict:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/auth/mcp/authorize",
        "token_endpoint": f"{ISSUER}/auth/mcp/token",
        "registration_endpoint": f"{ISSUER}/auth/mcp/register",
        "revocation_endpoint": f"{ISSUER}/auth/mcp/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": list(mcp_oauth.AUTH_METHODS),
        "revocation_endpoint_auth_methods_supported": list(mcp_oauth.AUTH_METHODS),
        "scopes_supported": [mcp_oauth.SCOPE],
        "service_documentation": f"{ISSUER}/help#ai-apps",
    }


@mcp_wellknown_bp.route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
@mcp_wellknown_bp.route("/.well-known/oauth-authorization-server/<path:_resource>", methods=["GET", "OPTIONS"])
@mcp_wellknown_bp.route("/.well-known/openid-configuration", methods=["GET", "OPTIONS"])
def authorization_server_metadata(_resource=None):
    return _cors(jsonify(metadata()))


@mcp_oauth_bp.route("/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return _cors(jsonify({}))
    if _limited("register"):
        return _cors(_oauth_error(mcp_oauth.OAuthError("invalid_request", "Too many requests. Try again in a minute.", 429)))
    try:
        client = mcp_oauth.register_client(request.get_json(silent=True))
    except mcp_oauth.OAuthError as e:
        return _cors(_oauth_error(e))
    logger.info("AI app registered for sign-in: %s (%s)", client["client_name"], client["client_id"])
    response = jsonify(client)
    response.status_code = 201
    return _cors(response)


def _redirect_back(redirect_uri: str, params: dict):
    parts = urlsplit(redirect_uri)
    query = parse_qsl(parts.query, keep_blank_values=True) + [(k, v) for k, v in params.items() if v is not None]
    return redirect(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), "")))


CONSENT_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Allow {{ app_name }}? · Sorcerers Summit</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; background: #0f141b; color: #e6e8eb; font: 16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  main { max-width: 440px; margin: 0 auto; padding: 40px 16px; }
  .card { background: #171e27; border: 1px solid #2a3340; border-radius: 12px; padding: 24px; }
  h1 { font-size: 22px; margin: 0 0 8px; }
  .brand { color: #f5c542; font-family: Georgia, serif; font-style: italic; font-size: 20px; margin-bottom: 20px; }
  p { margin: 0 0 12px; color: #c3c8cf; }
  ul { margin: 0 0 16px; padding-left: 20px; color: #c3c8cf; }
  li { margin-bottom: 6px; }
  .who { font-size: 14px; color: #9aa3ad; margin-bottom: 16px; }
  .who a { color: #9aa3ad; }
  .buttons { display: flex; gap: 12px; margin-top: 20px; }
  button { flex: 1; font: inherit; font-weight: 600; padding: 12px; border-radius: 8px; cursor: pointer; border: 1px solid #2a3340; }
  .allow { background: #f5c542; color: #1a1a1a; border-color: #f5c542; }
  .deny { background: transparent; color: #e6e8eb; }
  .small { font-size: 13px; color: #8b949e; margin-top: 16px; }
</style></head>
<body><main>
  <div class="brand">Sorcerers Summit</div>
  <div class="card">
    <h1>Allow {{ app_name }}?</h1>
    <p class="who">Signed in as <strong>{{ username }}</strong> · <a href="/auth/logout?next={{ switch_next }}">Not you?</a></p>
    <p>{{ app_name }} will be able to read your own Summit data so it can coach you:</p>
    <ul>
      <li>your ranked match history, including this season's newest games</li>
      <li>your Card Stats, even if they are private on your profile</li>
      <li>your own ranked deck lists</li>
    </ul>
    <p>It can't change anything, post for you or see anyone else's decks or private data.</p>
    <form method="post" action="/auth/mcp/authorize">
      {% for name, value in fields %}<input type="hidden" name="{{ name }}" value="{{ value }}">{% endfor %}
      <input type="hidden" name="csrf" value="{{ csrf }}">
      <div class="buttons">
        <button class="deny" type="submit" name="decision" value="deny">Cancel</button>
        <button class="allow" type="submit" name="decision" value="allow">Allow</button>
      </div>
    </form>
    <p class="small">You can disconnect it at any time from the Use Summit in AI apps section of the Help page.</p>
  </div>
</main></body></html>"""

ERROR_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Sign-in problem · Sorcerers Summit</title>
<style>body{margin:0;background:#0f141b;color:#e6e8eb;font:16px/1.5 system-ui,sans-serif}
main{max-width:440px;margin:0 auto;padding:40px 16px}a{color:#f5c542}</style></head>
<body><main><h1>Couldn't sign in</h1><p>{{ message }}</p><p><a href="/help#ai-apps">How to connect an AI app</a></p></main></body></html>"""

_FIELDS = ("client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method", "response_type",
           "resource", "scope")


@mcp_oauth_bp.route("/authorize", methods=["GET", "POST"])
def authorize():
    args = request.args if request.method == "GET" else request.form
    try:
        req = mcp_oauth.check_authorize_request(args)
    except mcp_oauth.OAuthError as e:
        return render_template_string(ERROR_PAGE, message=e.description), 400
    if "error" in req:
        code, description = req["error"]
        return _redirect_back(req["redirect_uri"], {"error": code, "error_description": description,
                                                    "state": req["state"]})

    user_id = session.get("user_id")
    if not user_id:
        # The site's own login page: Discord, Google or an email code, then back here
        return redirect("/login?" + urlencode({"next": request.full_path if request.method == "GET" else "/"}))

    if request.method == "GET":
        csrf = secrets.token_urlsafe(24)
        session["mcp_oauth_csrf"] = csrf
        fields = [(name, args.get(name)) for name in _FIELDS if args.get(name)]
        response = render_template_string(
            CONSENT_PAGE,
            app_name=req["client"]["client_name"] or "An AI app",
            username=session.get("username") or "you",
            switch_next=quote("/login?" + urlencode({"next": request.full_path}), safe=""),
            fields=fields,
            csrf=csrf,
        )
        return response, 200, {"Cache-Control": "no-store", "X-Frame-Options": "DENY"}

    expected = session.pop("mcp_oauth_csrf", None)
    if not expected or not secrets.compare_digest(expected, request.form.get("csrf") or ""):
        return render_template_string(ERROR_PAGE, message="This page expired. Start the sign-in again from your AI app."), 400
    if request.form.get("decision") != "allow":
        return _redirect_back(req["redirect_uri"], {"error": "access_denied",
                                                    "error_description": "The player cancelled.",
                                                    "state": req["state"]})
    code = mcp_oauth.create_code(req["client"]["client_id"], str(user_id), req["redirect_uri"],
                                 req["code_challenge"], req["resource"])
    logger.info("Player %s allowed AI app %s", user_id, req["client"]["client_id"])
    return _redirect_back(req["redirect_uri"], {"code": code, "state": req["state"], "iss": ISSUER})


def _basic_auth() -> tuple[str, str] | None:
    auth = request.authorization
    if auth and auth.type == "basic" and auth.username:
        return auth.username, auth.password or ""
    return None


@mcp_oauth_bp.route("/token", methods=["POST", "OPTIONS"])
def token():
    if request.method == "OPTIONS":
        return _cors(jsonify({}))
    if _limited("token"):
        return _cors(_oauth_error(mcp_oauth.OAuthError("invalid_request", "Too many requests. Try again in a minute.", 429)))
    try:
        tokens = mcp_oauth.exchange(request.form.to_dict(), _basic_auth())
    except mcp_oauth.OAuthError as e:
        return _cors(_oauth_error(e))
    response = jsonify(tokens)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return _cors(response)


@mcp_oauth_bp.route("/revoke", methods=["POST", "OPTIONS"])
def revoke():
    if request.method == "OPTIONS":
        return _cors(jsonify({}))
    mcp_oauth.revoke(request.form.get("token") or "")
    return _cors(jsonify({}))
