# Web-App Improvement Plan

Phased implementation plan derived from a code-quality assessment of `web-app/` (2026-05-06). Findings were cross-verified against the live nginx config and codebase to filter out false positives.

## Verified Issue List

### High Priority (Security/Correctness)

1. **Hardcoded Discord IDs with fallback defaults** — `webapp_config.py:71-72`. `DISCORD_GUILD_ID` and `CREATOR_ROLE_ID` should be required env vars, not defaulted.

### Medium Priority (Maintainability)

4. **God files** — `routes/api/players.py` (1962 LOC), `avatars.py` (1771), `cards.py` (1304).
5. **Raw `sqlite3` in route files** — 15+ route modules open connections directly instead of going through `repositories/`, contradicting the documented pattern.
6. **No standardized API error envelope** — routes return ad-hoc shapes; some default to implicit 500.
7. **Duplicated dynamic WHERE-clause builders** — `repositories/analytics.py`, `seasons.py`, `deck_rec_repo.py`.
8. **Sparse type hints** — most of `routes/`, `repositories/`, `services/`.
9. **Migrations use `print()`** — `migrations/create_analytics_tables.py:72,77`, `create_explorer_tables.py:73,78`.
10. **Oversized React pages with heavy local state** — `pages/AvatarDetail.jsx` (489 LOC, 15 `useState`s), `DeckRecommendations.jsx` (586 LOC).
11. **Missing UI error/loading states** — `AnalyticsSection.jsx:30`, `BannersSection.jsx:28` do `.catch(console.error)` with no fallback UI.
12. **Commented-out code** — `routes/api/matches.py`, `repositories/user_profiles.py`.
13. **Module-level caches without invalidation** — `routes/api/players.py:23-44`.

### Low Priority (Style/Coverage)

14. No PropTypes / TypeScript on the React frontend.
15. Thin frontend tests — ~12 test files for 40+ components.
16. Thin backend tests — 5 test files (~1194 LOC) for ~3000 LOC of routes/services.
17. Possibly unused dep `PuLP>=2.7.0` in `requirements.txt`.
18. API key-casing inconsistency (snake_case vs camelCase).

### False Positives (Excluded)

- **"Missing auth decorators"** — `tests/test_endpoint_auth.py` is a CI test that enforces every route either has an auth decorator or is explicitly listed in `KNOWN_PUBLIC_ENDPOINTS`.
- **"SQL injection via f-strings"** — interpolated fragments are hardcoded clauses or whitelisted column names; all user values use `?` parameter binding.

---

## Phase 0 — Security Hotfix (1–2 hours, ship today)

Goal: close the live admin bypass before anything else.

1. Remove `host.startswith("localhost")` clause from `utils/auth.py:82`. Replace with opt-in dev gate: `if os.getenv("DEV_MODE") == "1" and remote_addr in ("127.0.0.1", "::1"): return True`.
2. Add `ProxyFix` in `app.py`: `app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)`. Don't trust `X-Forwarded-Host`.
3. Promote env vars in `webapp_config.py:71-72` — fail fast if `DISCORD_GUILD_ID` / `CREATOR_ROLE_ID` are unset in production.
4. Add unit test: send `Host: localhost` to an admin-gated endpoint, assert 403.
5. Infra follow-up (track separately): add Cloudflare-IP allowlist on nginx `listen 80` or firewall the origin.

**Exit criteria**: tests green, deployed, admin bypass test passes.

---

## Phase 1 — Foundations for Refactor (1 week)

Goal: put guardrails in place before touching big files.

1. **Standard error envelope** — add `utils/errors.py` with `api_error(message, status, code=None)` and a Flask `errorhandler(Exception)`. Migrate routes opportunistically as touched.
2. **Test infrastructure**
   - Wire pytest coverage (`pytest --cov`) into CI, set a baseline (no threshold yet).
   - Add Vitest coverage to `pr-test-web.yml`.
3. **DB connection helper** — `utils/db.py` exposing `with get_conn(db_path) as conn:` context manager. No behavior change, just an available primitive.
4. **Logging cleanup** — replace `print()` in `migrations/create_analytics_tables.py` and `create_explorer_tables.py` with module loggers.
5. **Dead-code sweep** — remove commented blocks in `routes/api/matches.py`, `repositories/user_profiles.py`. Verify `PuLP` is unused (`grep -r pulp web-app/`); if so drop from `requirements.txt`.

**Exit criteria**: coverage reporting visible, error helper available, no `print()` in migrations.

---

## Phase 2 — Backend Decomposition (2–3 weeks)

Goal: shrink god files, push raw SQL behind repositories.

1. **Split `routes/api/players.py` (1962 LOC)** into `players_core.py`, `players_decks.py`, `players_stats.py`. Move business logic into `services/player_stats.py`. Replace module-level caches (`_card_image_map`, `_seed_decks`) with a `utils/cache.py` TTL cache or `functools.lru_cache` with explicit refresh.
2. **Split `routes/api/avatars.py` (1771 LOC)** into `avatars_core.py`, `avatars_stats.py`, `avatars_admin.py`. Extract avatar logic into `services/avatar.py`.
3. **Split `routes/api/cards.py` (1304 LOC)** along read vs admin lines; extract to `services/cards.py`.
4. **Migrate raw `sqlite3` in routes → repositories** — every `sqlite3.connect` in `routes/` moves into the matching repo class. Use `utils/db.py` context manager inside repositories.
5. **Query-builder helper** — `repositories/_query.py` with a small `where_clause(filters: dict, allowed: set)` builder. Migrate `analytics.py`, `seasons.py`, `deck_rec_repo.py` to use it.
6. **Type hints** — add return-type annotations to all `services/` and public repository methods. Run `mypy --ignore-missing-imports services/ repositories/` and fix what surfaces.

**Exit criteria**: no route file >500 LOC, no `sqlite3.connect` outside `repositories/` and `migrations/`, mypy passes for `services/` and `repositories/`.

---

## Phase 3 — Frontend Decomposition (1–2 weeks)

Goal: shrink large pages, fix silent UI failures.

1. **Refactor `pages/AvatarDetail.jsx`** — extract `useAvatarDetail` hook and split into `AvatarHeader`, `AvatarStats`, `AvatarMatchups`, `AvatarDecks` subcomponents. Collapse 15 `useState`s into a `useReducer`.
2. **Refactor `pages/DeckRecommendations.jsx`** — same pattern: hook for data, components for sections.
3. **Error boundaries** — add `<ErrorBoundary>` around `<Routes>` in `App.jsx`; replace `.catch(console.error)` in `AnalyticsSection.jsx`, `BannersSection.jsx`, and similar with toast/inline error UI.
4. **Loading skeletons** — adopt one shared `<LoadingState>` component for admin sections.
5. **API response naming** — pick snake_case for the wire format (matches Python), add a small `camelize()` shim in `frontend/src/api/` so React keeps camelCase internally without backend churn.

**Exit criteria**: no page component >400 LOC, every API call has a visible error path, naming consistent at the boundary.

---

## Phase 4 — Type Safety & Testing (2 weeks, parallelizable with Phase 3)

1. **TypeScript migration (incremental)** — add `tsconfig.json`, allow `.tsx` alongside `.jsx`, convert `frontend/src/api/` first (highest leverage), then shared components. Don't big-bang.
2. **Frontend tests** — add Vitest tests for: leaderboard rendering & sort, player search, deck listing, auth context. Target ~30 component tests.
3. **Backend integration tests** — add route-level tests for `players`, `avatars`, `cards`, `matches` covering happy path + auth failure. Target +20 tests.
4. **Coverage gate** — once baselines are established, set CI thresholds (e.g., 60% backend, 50% frontend) in `pr-test-web.yml`.

**Exit criteria**: `frontend/src/api/` is `.ts`, coverage gates active in CI.

---

## Phase 5 — Polish & Docs (a few days)

1. Update `CLAUDE.md` to reflect new layout (split route files, services, query helper).
2. Update `API_DOCUMENTATION.md` for the standardized error envelope.
3. Retro the `KNOWN_PUBLIC_ENDPOINTS` list — anything still public that shouldn't be?

---

## Sequencing & Risk

- Ship Phase 0 alone, in its own PR. Don't bundle with refactors.
- Phases 1 → 2 → 3 are sequential (each builds on the prior).
- Phase 4 can run in parallel with Phase 3 if a second contributor is available.
- Each route-split or repo migration in Phase 2 should be its own PR so reviews stay tractable; aim for ~300-line diffs.

**Total estimate**: 5–7 weeks of focused effort; Phase 0 alone is hours.
