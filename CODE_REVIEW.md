# SummitDiscordBot — Code Structure, Security & Duplication Review

Reviewed: full repo clone (web-app Flask/React, discord-bot, server scripts). 250 API routes parsed across 27 route modules (~15,400 lines in `web-app/routes/api/` alone).

---

## 1. Security Concerns

### 🔴 CRITICAL — `is_admin()` trusts the Host header (`web-app/utils/auth.py`)

```python
if remote_addr in ("127.0.0.1", "::1", "localhost") or host.startswith("localhost") or host.startswith("127.0.0.1"):
    return True
```

`request.host` comes from the client-supplied `Host` header. Your nginx configs use `proxy_set_header Host $host;`, which passes the client's Host header through. If the summit server block is (or ever becomes) nginx's default vhost — or if anyone hits the box by IP — a request with `Host: localhost` gets **full admin on every endpoint** decorated with `@require_admin`, plus `is_admin=True` in every template context. No credentials needed.

The `remote_addr` half is also fragile: gunicorn listens on a **unix socket**, so without `ProxyFix`, `remote_addr` for proxied traffic is not a meaningful client IP. Today it evaluates to empty (safe by accident), but adding ProxyFix later without removing this check would make `X-Forwarded-For: 127.0.0.1` an admin bypass.

**Fix:** delete the localhost/Host shortcut entirely from `is_admin()`. If you need a local-admin path for maintenance scripts, use the API key or a dedicated CLI entry point, not request-derived identity. If you add ProxyFix (you should, `x_for=1`), keep admin purely session/API-key based.

### 🔴 HIGH — API key grants blanket admin

In `is_admin()`, *any* valid `API_KEYS` entry is full admin. The docs say keys are handed to third parties for match reporting (e.g. draft-sorcery). Every integration key can therefore call `/api/admin/*`, download the store DB backup (`/api/store/.../backup` → `send_file`), merge/delete users, etc.

**Fix:** separate scopes — `API_KEYS` (reporting) vs `ADMIN_API_KEYS`, or per-key scope map. `DRAFT_SORCERY_API_KEY` already exists as a pattern; extend it. Also compare keys with `hmac.compare_digest` instead of `in` list (timing side-channel — minor, but free to fix).

### 🟠 HIGH — OAuth flows have no `state` parameter (`web-app/routes/auth.py`)

Neither the Discord nor Google flow generates/validates a `state` value. That enables login CSRF (attacker forces a victim's browser through a callback with the attacker's code, logging the victim into the attacker's account — nasty combined with the store: victim's saved address/orders land in the attacker-controlled account context, and vice versa).

**Fix:** generate `secrets.token_urlsafe(32)`, stash in session, send as `state`, verify on callback. ~6 lines per provider.

### 🟠 MEDIUM — No CSRF protection on state-changing endpoints

`Flask-WTF` is in `requirements.txt` but never imported. The only CSRF defense is `SESSION_COOKIE_SAMESITE='Lax'`. Lax does block cross-site POSTs from most vectors, but it's a single layer, doesn't cover older browsers, and any future GET endpoint with side effects is unprotected. For a session-cookie-authenticated JSON API, either enable `CSRFProtect` with a token header, or enforce a custom-header check (`X-Requested-With`) server-side for session-authed writes.

### 🟠 MEDIUM — Public analytics ingestion with no rate limiting

`POST /api/analytics/page-view`, `/banner-click`, `/heartbeat` are intentionally unauthenticated and write straight to SQLite with attacker-controlled `path`, `referrer`, `User-Agent`. Nothing in the app rate-limits (no Flask-Limiter; nginx configs define no `limit_req` for these). One `while true; do curl ...; done` fills `analytics.db` and skews every admin dashboard.

**Fix:** nginx `limit_req` zone on `/api/analytics/`, cap stored string lengths, and consider a rolling table size cap.

### 🟡 Worth fixing

- **Migrations run at import with blanket `except Exception`** (`app.py`): a failed migration logs an error and the app serves traffic against a half-migrated schema. Fail fast in production, or at least gate startup on critical tables.
- **`TEMPLATES_AUTO_RELOAD=True` + `SEND_FILE_MAX_AGE_DEFAULT=0`** are set unconditionally — dev conveniences running in production (perf, not security).
- **Unpinned dependencies** (`>=` everywhere, no lock file for Python). A `pip install` on redeploy can silently pull a breaking or compromised release. Pin exact versions or add `pip-compile`/`uv lock`.
- **Dead deps**: `Flask-Login`, `Flask-WTF`, `tiktoken` appear unused in web-app — remove or use them (each is attack surface + install time).
- **Hardcoded Discord guild/role IDs as config defaults** (`webapp_config.py`): the free-shipping role IDs and guild ID defaults belong in env/config data, not source — mostly a hygiene/portability issue.
- **Upload validation is extension-only.** UUID filenames kill path traversal (good), but a `.png` containing HTML is stored and served from your origin. Add magic-byte sniffing (`imghdr`/Pillow verify) and ensure nginx serves `/static/uploads/` with `Content-Type` from extension + `X-Content-Type-Options: nosniff` (svg correctly not allowed — keep it that way).
- **`session["discord_roles"]` cached at login** for free-shipping/creator checks — role revocations don't take effect for up to the 30-day session lifetime. Re-fetch roles on sensitive actions (checkout) or shorten session life.

### ✅ Things done well (worth saying)

- Parameterized SQL throughout — every f-string SQL I checked interpolates only hardcoded table names or whitelisted column sets (`curios.update_entry`, `fart` repos use `allowed` sets correctly). No injection found.
- Stripe integration is textbook: webhook signature verification, webhook-only order fulfillment, amount/currency mismatch flagging, restock on expiry.
- Open-redirect protection on post-login `next` URLs.
- Upload filenames are UUIDs; `SECRET_KEY` enforced in production; secure/httponly/samesite cookie flags set; debug mode env-gated.
- No `eval`/`exec`/`os.system`/pickle, no `|safe` in templates, no `dangerouslySetInnerHTML` in React.
- No secrets committed (checked git index + entropy scan).

---

## 2. Code Structure Review

The README claims a layered architecture (routes → services → repositories). The skeleton is there, but it's honored inconsistently:

**Routes layer does direct DB access — 67 `sqlite3.connect` calls inside `web-app/routes/api/`.** Worst offenders: `avatars.py` (22), `players.py` (12), `cards.py` (9), `admin.py` (8). These route files open connections, build SQL, and post-process rows inline — that's repository work. Consequence: connection handling, archive-table fallback logic (`for table in ("match_records", "match_records_archive")` with `except sqlite3.OperationalError: pass`) and JSON deck parsing are re-implemented per endpoint.

**Monolith route files.** `players.py` is 2,930 lines and `avatars.py` 2,600 — each larger than some whole services. Split by concern (e.g. `players/profile.py`, `players/privacy.py`, `players/stats.py`) or, minimally, push the query logic into the existing repositories.

**The discord-bot side is worse on this axis:** cogs contain ~135 direct `sqlite3.connect` calls (`shop.py` 35, `fun.py` 20, `lfg/cog.py` 18, `lfg/persistent_confirm.py` 16) despite `discord-bot/repositories/` existing. Also note the cogs use synchronous sqlite3 inside async discord.py handlers — each query blocks the event loop; consider `aiosqlite` or `asyncio.to_thread` for the hot paths.

**Silent exception swallowing** is a recurring pattern: `except sqlite3.OperationalError: pass` and `except Exception: pass` appear throughout routes and services. Missing-table fallbacks are legitimate, but swallowing *all* operational errors hides real corruption/locking issues. Centralize the "query with archive fallback" pattern in one repository helper that logs.

**Repo hygiene:** ~190MB of data is committed — a 73MB `.docx` rulebook, 40MB `top-8-decks-by-event`, 648KB test JSON, plus one-off maintenance scripts at repo root (`check_db.py`, `check_elo_only.py`, `check_matches.py`, `verify_matches.py`, `rename_event.py`, `recalculate_event_elo.py`). Move data to releases/Git LFS/object storage and scripts into `discord-bot/tools/` (which already exists).

**Config-as-code:** `EVENT_RATINGS` / `EVENT_NAME_MAPPINGS` / `SEASON_FILTERS` are large hand-maintained dicts in `webapp_config.py` that clearly change every event. They belong in the DB (there's already an events repo) or a data file, so adding an event doesn't require a deploy.

---

## 3. Duplication & Merge Opportunities

### Cross-project duplication (discord-bot ↔ web-app)

These files implement the same domain against the same databases in both projects, and have already drifted apart:

| discord-bot | web-app | similarity | notes |
|---|---|---|---|
| `repositories/blocked_users_repo.py` (72) | `repositories/blocked_users_repo.py` (117) | ~37% | same table, drifted feature sets |
| `repositories/limited_repo.py` (851) | `repositories/limited_repo.py` (863) | ~26% | biggest risk — 850 lines each against the same schema |
| `repositories/community_repo.py` (164) | `repositories/community.py` (136) | ~21% | |
| `services/limited_service.py` (448) | `services/limited_service.py` (259) | ~31% | duplicated business rules (run lifecycle) |

The web-app already does `sys.path.append(discord-bot)` to borrow utilities — the coupling exists, it's just informal. **Recommendation:** create a `summit_core/` package (repositories + shared services + db path config) that both apps import. Start with `limited_repo` — two 850-line files enforcing the same arena rules independently is where a rules bug will bite first (e.g. one side changes max losses and the other doesn't).

### Duplication within web-app routes

Identical/near-identical helper functions copy-pasted across route files:

- `has_deck_data()` — **4 copies**
- `elo_bracket()` — **4 copies**
- `_get_card_image_map()` / `_resolve_card_image()` / `_find_card_image` — **3 copies each** (card-image lookup logic re-implemented in `cards.py`, `players.py`, and elsewhere)
- `_get_event_date_range()` — **3 copies**
- The `match_records` + `match_records_archive` dual-table query loop — dozens of inline copies

Move these into `web-app/utils/` (e.g. `utils/elo_display.py`, `utils/card_images.py`) or the relevant repository. The card-image map is also a caching opportunity — several endpoints rebuild it per request from the 648KB `All_Cards_Array.json`.

- `ALLOWED_IMAGE_EXTENSIONS` + max-size + save-with-uuid upload logic is triplicated (`analytics.py`, `store.py`, `curios.py`) → one `utils/uploads.py:save_image(file, dest_dir)`.
- Two upload-to-server scripts (`server/upload_to_server.bat` + `.ps1`) do the same job — keep one.

### Duplicate endpoints

Route names like `get_leaderboard` (×3), `create_season`/`delete_season` (×3), `report_match` (×2), `search_opponents` (×2) exist across modules (main vs limited vs explorer variants). That's partly legitimate domain separation, but the season CRUD trio (seasons / explorer / limited) is a candidate for one parameterized seasons service.

---

## 4. Suggested priority order

1. Remove localhost/Host bypass from `is_admin()` + add ProxyFix — small diff, closes the worst hole.
2. Scope API keys (reporting vs admin) + `compare_digest`.
3. Add OAuth `state` to both providers.
4. Rate-limit `/api/analytics/*` at nginx.
5. Extract shared route helpers (`elo_bracket`, card-image map, archive-query helper) — mechanical, low-risk.
6. `summit_core` shared package, starting with `limited_repo`.
7. Split `players.py`/`avatars.py`, move their SQL into repositories.
8. Pin dependencies; drop unused ones; move big data files out of git.

---

## 5. OpenAPI spec

`openapi.yaml` (OpenAPI 3.1, validates clean) covers all 250 discovered routes / 221 paths, generated from the actual Flask route decorators:

- Correct blueprint prefixes (`/api/match-report`, `/api/limited`, `/api/curios`, etc.)
- Typed path parameters from Flask converters (`<int:x>` → integer)
- Security schemes: `ApiKeyAuth` (X-API-Key), `BearerAuth`, `SessionAuth` (cookie), applied per-endpoint from the `@require_*` decorators, plus a heuristic for handlers doing inline `session.get("user_id")` checks
- Tags per module with descriptions; summaries pulled from handler docstrings
- Full request schemas for the externally documented endpoints (`/api/report-external-match`, `/api/match-report/submit`); everything else has a generic object body pointing at the source handler to refine

Note the spec is honest about a finding: some endpoints show no security requirement because auth is enforced inline in the handler body rather than by decorator — worth normalizing to decorators so the spec (and auditing) stays trustworthy.
