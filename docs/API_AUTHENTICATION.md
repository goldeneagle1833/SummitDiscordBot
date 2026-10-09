# API Authentication — what changed and how to update your calls

**TL;DR:** Every request to `https://sorcererssummit.com/api/...` now needs an API key.
Add one header and you're done:

```
X-API-Key: <your key>
```

Requests without it get `401 Unauthorized` before the endpoint runs. Nothing about the
endpoints themselves (paths, parameters, response shapes) has changed.

---

## What changed

Until now, most read endpoints (leaderboards, match history, player profiles, card/avatar
stats, events, brackets, decks, seasons, …) were open to anyone. They are now locked down:
**no `/api/*` route answers without credentials.**

| Before | After |
|---|---|
| ~190 read endpoints were open to the public | All `/api/*` routes require an API key |
| Only write/admin endpoints needed a key or login | Per-endpoint admin/login rules still apply *on top of* the key |
| `401` only for missing login/admin | `401 {"code": "api_key_required"}` for any call without a key |

The Sorcerers Summit website itself keeps working for visitors through a separate
same-site cookie mechanism. That path is **not** available to third-party code — if you're
calling the API from your own server, script, bot, or app, you need a key.

## How to authenticate

Send your key on **every** request, using either header form:

```http
X-API-Key: sk_live_example
```
or
```http
Authorization: Bearer sk_live_example
```

Examples:

```bash
# curl
curl -H "X-API-Key: $SUMMIT_API_KEY" https://sorcererssummit.com/api/leaderboard
```

```python
# Python (requests)
import os, requests

session = requests.Session()
session.headers["X-API-Key"] = os.environ["SUMMIT_API_KEY"]

r = session.get("https://sorcererssummit.com/api/leaderboard")
r.raise_for_status()
print(r.json())
```

```python
# Python (aiohttp)
async with aiohttp.ClientSession(headers={"X-API-Key": SUMMIT_API_KEY}) as session:
    async with session.get("https://sorcererssummit.com/api/player/123") as resp:
        data = await resp.json()
```

```js
// Node / fetch
const res = await fetch('https://sorcererssummit.com/api/match-history', {
  headers: { 'X-API-Key': process.env.SUMMIT_API_KEY },
})
```

If you already have a key for the write endpoints (match reporting, matchmaking relay,
limited arena), **the same key works everywhere** — just send it on your read calls too.

## How to tell your calls are affected

Any call that previously worked without a key will now return:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: ApiKey realm="summit"
Content-Type: application/json

{"error": "An API key is required. Pass it in the X-API-Key header.", "code": "api_key_required"}
```

Other responses you may see:

| Status | `code` | Meaning |
|---|---|---|
| `401` | `api_key_required` | No key sent. Add the header. |
| `401` | `invalid_api_key` | A key was sent but it isn't valid. Check for typos / stale keys. |
| `401` | *(no code)* `"Not authenticated"` | Key is fine; this endpoint also needs a logged-in user session. |
| `403` | — | Key is fine; this endpoint needs admin or a specific role. |

A quick way to find every affected call in a codebase: grep for `sorcererssummit.com/api`
(or your base-URL constant) and make sure each request path sets the header. The simplest
fix is usually to set it once on a shared HTTP client/session, as in the examples above.

## Endpoints that do NOT need a key

Only three routes stay open, and none of them return data:

| Route | Why |
|---|---|
| `GET /api/health` | Uptime checks. Returns pass/fail only. |
| `POST /api/store/webhooks/stripe` | Verified by Stripe's signature instead. |
| `GET /api/site-token` | Internal; issues the website's own cookie. Not usable from outside. |

Everything else under `/api/` — including every endpoint listed in `openapi.yaml` — needs
the key.

## Getting a key

Keys are issued by the Summit maintainer (goldeneagle1833). Keep it out of source control:
put it in an environment variable or secret store, and send it only over HTTPS.

## FAQ

**Do I need to change any URLs, query params, or parse responses differently?**
No. Only the header is new.

**My calls come from a browser page on another site.**
That won't work — browser cross-site requests have no way to carry a key safely. Proxy
through your own backend and attach the key there.

**I'm calling `/api/health` for monitoring.**
No change needed; it stays open.

**Can I check my key works without touching real data?**
Yes: `curl -H "X-API-Key: $KEY" https://sorcererssummit.com/api/status` returns
`{"status": "online", ...}` with a valid key and `401` without.
