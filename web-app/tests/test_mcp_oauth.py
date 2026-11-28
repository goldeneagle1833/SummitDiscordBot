"""Sign-in for AI apps: OAuth 2.1 flow (register, authorize, token, refresh, revoke) and the
/api/mcp/me endpoints a signed-in AI app reads."""

import base64
import hashlib
import re
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest

import webapp_config
from services import mcp_oauth

REDIRECT = "https://claude.ai/api/mcp/auth_callback"
PLAYER = "111111111111111111"


@pytest.fixture(autouse=True)
def oauth_db(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp_config, "MCP_AUTH_DB_PATH", tmp_path / "mcp_auth.db")
    from services import ranked_analytics
    ranked_analytics._client_hits.clear()
    yield


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _register(client, **extra):
    r = client.post("/auth/mcp/register", json={"client_name": "Claude", "redirect_uris": [REDIRECT], **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _sign_in(client, user_id=PLAYER):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "Pete"


def _authorize_params(client_id, challenge, state="xyz"):
    return {"client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
            "resource": "https://sorcererssummit.com/mcp/account"}


def _get_code(client, client_id, challenge):
    page = client.get("/auth/mcp/authorize", query_string=_authorize_params(client_id, challenge))
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Allow Claude?" in html and "Pete" in html
    csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    r = client.post("/auth/mcp/authorize", data={**_authorize_params(client_id, challenge),
                                                 "csrf": csrf, "decision": "allow"})
    assert r.status_code == 302
    back = urlsplit(r.headers["Location"])
    assert f"{back.scheme}://{back.netloc}{back.path}" == REDIRECT
    query = parse_qs(back.query)
    assert query["state"] == ["xyz"]
    return query["code"][0]


def _full_flow(client):
    reg = _register(client)
    verifier, challenge = _pkce()
    _sign_in(client)
    code = _get_code(client, reg["client_id"], challenge)
    r = client.post("/auth/mcp/token", data={"grant_type": "authorization_code", "code": code,
                                             "redirect_uri": REDIRECT, "client_id": reg["client_id"],
                                             "code_verifier": verifier})
    assert r.status_code == 200, r.get_json()
    return reg, r.get_json(), code, verifier


def test_discovery_document(client):
    data = client.get("/.well-known/oauth-authorization-server").get_json()
    assert data["authorization_endpoint"].endswith("/auth/mcp/authorize")
    assert data["code_challenge_methods_supported"] == ["S256"]
    assert data["registration_endpoint"].endswith("/auth/mcp/register")
    # Path-style lookup for /mcp/account works too (RFC 8414 section 3.1)
    assert client.get("/.well-known/oauth-authorization-server/mcp/account").status_code == 200


def test_register_rejects_bad_redirects(client):
    r = client.post("/auth/mcp/register", json={"redirect_uris": ["http://evil.example/cb"]})
    assert r.status_code == 400
    assert client.post("/auth/mcp/register", json={"redirect_uris": []}).status_code == 400
    assert client.post("/auth/mcp/register", json={"redirect_uris": ["http://localhost:3333/cb"]}).status_code == 201


def test_signed_out_player_goes_to_the_site_login_page(client):
    reg = _register(client)
    _, challenge = _pkce()
    r = client.get("/auth/mcp/authorize", query_string=_authorize_params(reg["client_id"], challenge))
    assert r.status_code == 302
    location = r.headers["Location"]
    assert location.startswith("/login?next=")
    # Back to this same authorize page after Discord, Google or an email code
    assert "%2Fauth%2Fmcp%2Fauthorize" in location


def test_full_sign_in_and_me_endpoint(client):
    reg, tokens, _, _ = _full_flow(client)
    assert tokens["token_type"] == "Bearer" and tokens["refresh_token"]
    me = client.get("/api/mcp/me", headers={"X-Summit-User-Token": tokens["access_token"]})
    assert me.status_code == 200, me.get_json()
    assert me.get_json()["player_id"] == PLAYER
    assert me.get_json()["app"] == "Claude"


def test_me_needs_a_token(client):
    assert client.get("/api/mcp/me").status_code == 401
    assert client.get("/api/mcp/me", headers={"X-Summit-User-Token": "nope"}).status_code == 401


def test_pkce_is_required_and_checked(client):
    reg = _register(client)
    _sign_in(client)
    params = _authorize_params(reg["client_id"], "x")
    params.pop("code_challenge")
    r = client.get("/auth/mcp/authorize", query_string=params)
    assert r.status_code == 302 and "error=invalid_request" in r.headers["Location"]

    verifier, challenge = _pkce()
    code = _get_code(client, reg["client_id"], challenge)
    r = client.post("/auth/mcp/token", data={"grant_type": "authorization_code", "code": code,
                                             "client_id": reg["client_id"], "code_verifier": "wrong"})
    assert r.status_code == 400 and r.get_json()["error"] == "invalid_grant"


def test_code_works_once_and_replay_cancels_the_tokens(client):
    reg, tokens, code, verifier = _full_flow(client)
    again = client.post("/auth/mcp/token", data={"grant_type": "authorization_code", "code": code,
                                                 "client_id": reg["client_id"], "code_verifier": verifier})
    assert again.status_code == 400
    assert client.get("/api/mcp/me", headers={"X-Summit-User-Token": tokens["access_token"]}).status_code == 401


def test_refresh_rotates_and_old_refresh_token_ends_the_sign_in(client):
    reg, tokens, _, _ = _full_flow(client)
    r = client.post("/auth/mcp/token", data={"grant_type": "refresh_token", "client_id": reg["client_id"],
                                             "refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    fresh = r.get_json()
    assert fresh["refresh_token"] != tokens["refresh_token"]
    assert client.get("/api/mcp/me", headers={"X-Summit-User-Token": fresh["access_token"]}).status_code == 200
    # Reusing the old refresh token looks like theft: everything from this sign-in stops working
    r = client.post("/auth/mcp/token", data={"grant_type": "refresh_token", "client_id": reg["client_id"],
                                             "refresh_token": tokens["refresh_token"]})
    assert r.status_code == 400
    assert client.get("/api/mcp/me", headers={"X-Summit-User-Token": fresh["access_token"]}).status_code == 401


def test_cancel_sends_access_denied(client):
    reg = _register(client)
    _, challenge = _pkce()
    _sign_in(client)
    page = client.get("/auth/mcp/authorize", query_string=_authorize_params(reg["client_id"], challenge))
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    r = client.post("/auth/mcp/authorize", data={**_authorize_params(reg["client_id"], challenge),
                                                 "csrf": csrf, "decision": "deny"})
    assert "error=access_denied" in r.headers["Location"]


def test_consent_needs_the_page_token(client):
    reg = _register(client)
    _, challenge = _pkce()
    _sign_in(client)
    r = client.post("/auth/mcp/authorize", data={**_authorize_params(reg["client_id"], challenge),
                                                 "decision": "allow"})
    assert r.status_code == 400


def test_unknown_redirect_uri_is_never_followed(client):
    reg = _register(client)
    _sign_in(client)
    params = _authorize_params(reg["client_id"], "c")
    params["redirect_uri"] = "https://evil.example/steal"
    r = client.get("/auth/mcp/authorize", query_string=params)
    assert r.status_code == 400
    assert "evil.example" not in r.headers.get("Location", "")


def test_confidential_client_needs_its_secret(client):
    reg = _register(client, token_endpoint_auth_method="client_secret_post")
    assert reg["client_secret"]
    verifier, challenge = _pkce()
    _sign_in(client)
    code = _get_code(client, reg["client_id"], challenge)
    base = {"grant_type": "authorization_code", "code": code, "client_id": reg["client_id"], "code_verifier": verifier}
    assert client.post("/auth/mcp/token", data=base).status_code == 401
    assert client.post("/auth/mcp/token", data={**base, "client_secret": reg["client_secret"]}).status_code == 200


def test_revoke_and_player_disconnect(client):
    reg, tokens, _, _ = _full_flow(client)
    listed = client.get("/api/mcp/connections").get_json()["connections"]
    assert [c["name"] for c in listed] == ["Claude"]
    client.delete(f"/api/mcp/connections/{reg['client_id']}")
    assert client.get("/api/mcp/me", headers={"X-Summit-User-Token": tokens["access_token"]}).status_code == 401
    assert client.get("/api/mcp/connections").get_json()["connections"] == []

    _, tokens2, _, _ = _full_flow(client)
    client.post("/auth/mcp/revoke", data={"token": tokens2["refresh_token"]})
    assert client.get("/api/mcp/me", headers={"X-Summit-User-Token": tokens2["access_token"]}).status_code == 401


def test_tokens_are_stored_hashed(client):
    _, tokens, _, _ = _full_flow(client)
    raw = webapp_config.MCP_AUTH_DB_PATH.read_bytes()
    assert tokens["access_token"].encode() not in raw
    assert tokens["refresh_token"].encode() not in raw


def test_my_matches_include_newest_games(client, match_db, monkeypatch):
    import json
    import sqlite3
    from services import data_release, public_match_history as history

    history.clear_cache()
    monkeypatch.setattr(data_release, "cutoff_timestamp", lambda now=None: "2027-02-01T00:00:00")
    deck = json.dumps({"avatar": [{"name": "Sparkmage", "type": "Avatar"}],
                       "spellbook": [{"name": "Spark", "elements": "Fire"}]})
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO match_records (winner_id, winner_display_name, losser_id, losser_display_name, timestamp,"
        " match_type, json_deck_data_winner, json_deck_data_loser, curiosa_url_winner) VALUES"
        " (?, 'Pete', '222', 'Amy', '2027-02-05T10:00:00', 'ranked', ?, ?, 'https://curiosa.io/decks/secret')",
        (PLAYER, deck, deck))
    conn.commit()
    conn.close()

    _, tokens, _, _ = _full_flow(client)
    data = client.get("/api/mcp/me/matches", headers={"X-Summit-User-Token": tokens["access_token"]}).get_json()
    assert data["matches"][0]["player"]["avatar"] == "Sparkmage"  # not held back for the owner
    assert "secret" not in json.dumps(data)
    # The open API still holds it back
    history.clear_cache()
    public = client.get(f"/api/public/players/{PLAYER}/matches?site=https://x.example").get_json()
    assert public["matches"][0]["player"]["avatar"] is None
    history.clear_cache()


def test_my_card_stats(client):
    _, tokens, _, _ = _full_flow(client)
    r = client.get("/api/mcp/me/card-stats", headers={"X-Summit-User-Token": tokens["access_token"]})
    assert r.status_code == 200
    assert r.get_json()["queue"] == "ranked"


def test_my_decks_are_own_only(client, match_db):
    import json
    import sqlite3
    from services import public_match_history as history

    history.clear_cache()
    mine = json.dumps({"avatar": [{"name": "Sparkmage", "type": "Avatar"}],
                       "spellbook": [{"name": "Spark", "elements": "Fire", "quantity": 4}],
                       "atlas": [{"name": "Volcano", "quantity": 2}]})
    theirs = json.dumps({"avatar": [{"name": "Druid", "type": "Avatar"}],
                         "spellbook": [{"name": "Secret Opponent Card", "elements": "Earth", "quantity": 3}]})
    conn = sqlite3.connect(str(match_db))
    for ts, winner, loser, wj, lj in [
        ("2026-11-01T10:00:00", PLAYER, "222", mine, theirs),
        ("2026-11-02T10:00:00", "222", PLAYER, theirs, mine),
    ]:
        conn.execute(
            "INSERT INTO match_records (winner_id, winner_display_name, losser_id, losser_display_name, timestamp,"
            " match_type, json_deck_data_winner, json_deck_data_loser) VALUES (?, 'A', ?, 'B', ?, 'ranked', ?, ?)",
            (winner, loser, ts, wj, lj))
    conn.commit()
    conn.close()

    _, tokens, _, _ = _full_flow(client)
    data = client.get("/api/mcp/me/decks", headers={"X-Summit-User-Token": tokens["access_token"]}).get_json()
    assert len(data["decks"]) == 1
    deck = data["decks"][0]
    assert deck["avatar"] == "Sparkmage" and deck["games"] == 2 and deck["wins"] == 1
    assert deck["cards"]["spellbook"] == [{"name": "Spark", "quantity": 4}]
    assert "Secret Opponent Card" not in json.dumps(data)
    assert client.get("/api/mcp/me/decks").status_code == 401
    # The open API never carries deck lists
    history.clear_cache()
    public = client.get(f"/api/public/players/{PLAYER}/matches?site=https://x.example").get_json()
    assert "Spark\"" not in json.dumps(public) and "_own_deck" not in json.dumps(public)
    history.clear_cache()
