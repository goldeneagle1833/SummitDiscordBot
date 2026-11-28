"""Sign-in for AI apps (OAuth 2.1 authorization server for the Summit MCP server).

An AI app (Claude, ChatGPT, ...) that adds the signed-in connector
(https://sorcererssummit.com/mcp/account) is sent here to sign in:

1. The app registers itself (dynamic client registration, RFC 7591).
2. It opens /auth/mcp/authorize in the player's browser. A player who is not
   signed in goes to the site's normal /login page first, so every way of
   signing in works (Discord, Google, email code). Then they see an
   "Allow <app>?" screen.
3. On Allow, the app gets a one-time code and swaps it at /auth/mcp/token
   (PKCE S256 required) for an access token (1 hour) and a refresh token
   (30 days, replaced on every use).

What a token can do: read that player's own data through the /api/mcp/me
endpoints, nothing else. It can't change anything, can't act as the player on
the site and is never an admin, even for an admin's account.

Only hashes of codes, tokens and client secrets are stored, in their own
small database (MCP_AUTH_DB_PATH).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

import webapp_config

SCOPE = "summit:read"
CODE_SECONDS = 10 * 60
ACCESS_SECONDS = 60 * 60
REFRESH_SECONDS = 30 * 24 * 60 * 60
MAX_REDIRECT_URIS = 10
MAX_CLIENTS = 5000
AUTH_METHODS = ("none", "client_secret_post", "client_secret_basic")


class OAuthError(Exception):
    """An OAuth error response: ``error`` code (RFC 6749) and a readable description."""

    def __init__(self, error: str, description: str, status: int = 400):
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status

    def body(self) -> dict:
        return {"error": self.error, "error_description": self.description}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> int:
    return int(time.time())


def _connect(db_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or webapp_config.MCP_AUTH_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mcp_clients (
            client_id TEXT PRIMARY KEY,
            client_name TEXT,
            redirect_uris TEXT NOT NULL,
            auth_method TEXT NOT NULL DEFAULT 'none',
            secret_hash TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mcp_codes (
            code_hash TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            code_challenge TEXT NOT NULL,
            resource TEXT,
            expires_at INTEGER NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS mcp_tokens (
            token_hash TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            client_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            grant_id TEXT NOT NULL,
            resource TEXT,
            expires_at INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mcp_tokens_grant ON mcp_tokens (grant_id);
        CREATE INDEX IF NOT EXISTS idx_mcp_tokens_user ON mcp_tokens (user_id);
        """
    )
    return conn


def _cleanup(conn: sqlite3.Connection) -> None:
    now = _now()
    conn.execute("DELETE FROM mcp_codes WHERE expires_at < ?", (now - 3600,))
    conn.execute("DELETE FROM mcp_tokens WHERE expires_at < ?", (now - 86400,))


# ---------------------------------------------------------------------------
# Clients (dynamic registration)
# ---------------------------------------------------------------------------


def _valid_redirect_uri(uri: str) -> bool:
    try:
        parts = urlsplit(uri)
    except ValueError:
        return False
    if parts.fragment or not parts.netloc:
        return False
    if parts.scheme == "https":
        return True
    # Desktop apps listen on the loopback address (RFC 8252)
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


def register_client(metadata: dict, db_path=None) -> dict:
    if not isinstance(metadata, dict):
        raise OAuthError("invalid_client_metadata", "Send the client details as JSON.")
    uris = metadata.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECT_URIS:
        raise OAuthError("invalid_redirect_uri", "redirect_uris must list 1 to 10 addresses.")
    if not all(isinstance(u, str) and len(u) <= 500 and _valid_redirect_uri(u) for u in uris):
        raise OAuthError("invalid_redirect_uri", "Redirect addresses must be https (or http on localhost).")
    method = metadata.get("token_endpoint_auth_method") or "none"
    if method not in AUTH_METHODS:
        raise OAuthError("invalid_client_metadata", f"token_endpoint_auth_method must be one of {AUTH_METHODS}.")
    grants = metadata.get("grant_types") or ["authorization_code", "refresh_token"]
    if "authorization_code" not in grants:
        raise OAuthError("invalid_client_metadata", "This server only supports the authorization_code grant.")
    name = str(metadata.get("client_name") or "An AI app").strip()[:80] or "An AI app"

    client_id = "mcp_" + secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32) if method != "none" else None
    now = _now()
    conn = _connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM mcp_clients").fetchone()[0] >= MAX_CLIENTS:
            # Forget registrations nobody ever finished signing in with
            conn.execute(
                "DELETE FROM mcp_clients WHERE created_at < ? AND client_id NOT IN "
                "(SELECT DISTINCT client_id FROM mcp_tokens)", (now - 86400,))
        conn.execute(
            "INSERT INTO mcp_clients (client_id, client_name, redirect_uris, auth_method, secret_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, name, json.dumps(uris), method, _hash(secret) if secret else None, now),
        )
        conn.commit()
    finally:
        conn.close()
    out = {
        "client_id": client_id,
        "client_id_issued_at": now,
        "client_name": name,
        "redirect_uris": uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": method,
        "scope": SCOPE,
    }
    if secret:
        out["client_secret"] = secret
        out["client_secret_expires_at"] = 0
    return out


def get_client(client_id: str, db_path=None) -> dict | None:
    if not client_id:
        return None
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM mcp_clients WHERE client_id = ?", (client_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {**dict(row), "redirect_uris": json.loads(row["redirect_uris"])}


def _check_client_secret(client: dict, secret: str | None) -> None:
    if client["auth_method"] == "none":
        return
    if not secret or not secrets.compare_digest(_hash(secret), client["secret_hash"] or ""):
        raise OAuthError("invalid_client", "Wrong client secret.", 401)


# ---------------------------------------------------------------------------
# Authorize
# ---------------------------------------------------------------------------


def check_authorize_request(args: dict, db_path=None) -> dict:
    """Validate the /authorize query. Errors before the redirect address is trusted raise OAuthError."""
    client = get_client(args.get("client_id"), db_path)
    if not client:
        raise OAuthError("invalid_client", "This app isn't registered. Remove and add the connector again.")
    redirect_uri = args.get("redirect_uri") or (client["redirect_uris"][0] if len(client["redirect_uris"]) == 1 else None)
    if redirect_uri not in client["redirect_uris"]:
        raise OAuthError("invalid_request", "The app's return address doesn't match its registration.")
    request = {
        "client": client,
        "redirect_uri": redirect_uri,
        "state": args.get("state"),
        "resource": args.get("resource"),
    }
    # From here on, errors go back to the app on its redirect address
    if args.get("response_type") != "code":
        request["error"] = ("unsupported_response_type", "Only response_type=code is supported.")
    elif not args.get("code_challenge") or args.get("code_challenge_method") != "S256":
        request["error"] = ("invalid_request", "PKCE with code_challenge_method=S256 is required.")
    else:
        request["code_challenge"] = args["code_challenge"]
    return request


def create_code(client_id: str, user_id: str, redirect_uri: str, code_challenge: str,
                resource: str | None, db_path=None) -> str:
    code = secrets.token_urlsafe(32)
    conn = _connect(db_path)
    try:
        _cleanup(conn)
        conn.execute(
            "INSERT INTO mcp_codes (code_hash, client_id, user_id, redirect_uri, code_challenge, resource, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_hash(code), client_id, str(user_id), redirect_uri, code_challenge, resource, _now() + CODE_SECONDS),
        )
        conn.commit()
    finally:
        conn.close()
    return code


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def _issue(conn: sqlite3.Connection, client_id: str, user_id: str, grant_id: str, resource: str | None) -> dict:
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = _now()
    conn.executemany(
        "INSERT INTO mcp_tokens (token_hash, kind, client_id, user_id, grant_id, resource, expires_at, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (_hash(access), "access", client_id, user_id, grant_id, resource, now + ACCESS_SECONDS, now),
            (_hash(refresh), "refresh", client_id, user_id, grant_id, resource, now + REFRESH_SECONDS, now),
        ],
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": ACCESS_SECONDS,
        "refresh_token": refresh,
        "scope": SCOPE,
    }


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def exchange(form: dict, basic_auth: tuple[str, str] | None = None, db_path=None) -> dict:
    """POST /auth/mcp/token for both grants."""
    client_id = form.get("client_id")
    secret = form.get("client_secret")
    if basic_auth:
        client_id, secret = basic_auth
    client = get_client(client_id, db_path)
    if not client:
        raise OAuthError("invalid_client", "Unknown client.", 401)
    _check_client_secret(client, secret)

    grant = form.get("grant_type")
    conn = _connect(db_path)
    try:
        if grant == "authorization_code":
            code = form.get("code") or ""
            row = conn.execute("SELECT * FROM mcp_codes WHERE code_hash = ?", (_hash(code),)).fetchone()
            if not row or row["client_id"] != client["client_id"]:
                raise OAuthError("invalid_grant", "That sign-in code isn't valid.")
            if row["used"]:
                # A replayed code: cancel everything it gave out (RFC 6749 4.1.2)
                conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE grant_id = ?", (row["code_hash"],))
                conn.commit()
                raise OAuthError("invalid_grant", "That sign-in code was already used.")
            if row["expires_at"] < _now():
                raise OAuthError("invalid_grant", "That sign-in code has expired. Sign in again.")
            if form.get("redirect_uri") and form["redirect_uri"] != row["redirect_uri"]:
                raise OAuthError("invalid_grant", "The return address doesn't match.")
            verifier = form.get("code_verifier") or ""
            if not verifier or not secrets.compare_digest(_s256(verifier), row["code_challenge"]):
                raise OAuthError("invalid_grant", "PKCE check failed.")
            conn.execute("UPDATE mcp_codes SET used = 1 WHERE code_hash = ?", (row["code_hash"],))
            tokens = _issue(conn, client["client_id"], row["user_id"], row["code_hash"], row["resource"])
            conn.commit()
            return tokens

        if grant == "refresh_token":
            token = form.get("refresh_token") or ""
            row = conn.execute(
                "SELECT * FROM mcp_tokens WHERE token_hash = ? AND kind = 'refresh'", (_hash(token),)
            ).fetchone()
            if not row or row["client_id"] != client["client_id"]:
                raise OAuthError("invalid_grant", "That refresh token isn't valid. Sign in again.")
            if row["revoked"]:
                # An old refresh token came back: someone may have copied it, end the whole sign-in
                conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE grant_id = ?", (row["grant_id"],))
                conn.commit()
                raise OAuthError("invalid_grant", "That refresh token was already used. Sign in again.")
            if row["expires_at"] < _now():
                raise OAuthError("invalid_grant", "Your sign-in has expired. Sign in again.")
            conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE token_hash = ?", (row["token_hash"],))
            tokens = _issue(conn, client["client_id"], row["user_id"], row["grant_id"], row["resource"])
            conn.commit()
            return tokens

        raise OAuthError("unsupported_grant_type", "Use authorization_code or refresh_token.")
    finally:
        conn.close()


def verify_access_token(token: str, db_path=None) -> dict | None:
    """{user_id, client_id, client_name, expires_at} for a live access token, else None."""
    if not token or len(token) > 200:
        return None
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT t.user_id, t.client_id, t.expires_at, t.revoked, c.client_name FROM mcp_tokens t"
            " LEFT JOIN mcp_clients c ON c.client_id = t.client_id"
            " WHERE t.token_hash = ? AND t.kind = 'access'",
            (_hash(token),),
        ).fetchone()
    finally:
        conn.close()
    if not row or row["revoked"] or row["expires_at"] < _now():
        return None
    return {"user_id": row["user_id"], "client_id": row["client_id"],
            "client_name": row["client_name"], "expires_at": row["expires_at"]}


def revoke(token: str, db_path=None) -> None:
    """RFC 7009: revoke the token and the rest of its sign-in. Unknown tokens are fine."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT grant_id FROM mcp_tokens WHERE token_hash = ?", (_hash(token or ""),)).fetchone()
        if row:
            conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE grant_id = ?", (row["grant_id"],))
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The player's own list of connected apps
# ---------------------------------------------------------------------------


def connections(user_id: str, db_path=None) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT t.client_id, c.client_name, MIN(t.created_at) AS first_at, MAX(t.created_at) AS last_at"
            " FROM mcp_tokens t LEFT JOIN mcp_clients c ON c.client_id = t.client_id"
            " WHERE t.user_id = ? AND t.kind = 'refresh' AND t.revoked = 0 AND t.expires_at > ?"
            " GROUP BY t.client_id ORDER BY last_at DESC",
            (str(user_id), _now()),
        ).fetchall()
    finally:
        conn.close()
    return [{"client_id": r["client_id"], "name": r["client_name"] or "An AI app",
             "connected_at": r["first_at"], "last_used_at": r["last_at"]} for r in rows]


def disconnect(user_id: str, client_id: str | None = None, db_path=None) -> int:
    conn = _connect(db_path)
    try:
        if client_id:
            cur = conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE user_id = ? AND client_id = ? AND revoked = 0",
                               (str(user_id), client_id))
        else:
            cur = conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (str(user_id),))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
