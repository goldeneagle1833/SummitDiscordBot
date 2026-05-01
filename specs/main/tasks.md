# Tasks: Flask/Jinja2 → React SPA Migration

**Input**: Design documents from `specs/main/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/ (auth, leaderboard, players, matches, events, decks), quickstart.md

**Tests**: Not explicitly requested — test tasks omitted.

**Organization**: Tasks are grouped by migration phase. Each phase produces an independently verifiable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story/phase this task belongs to (US1–US6)
- Include exact file paths in descriptions

## User Stories

- **US1**: Core Data Pages — Leaderboard, Player profiles, Match history (MVP)
- **US2**: Events & Decks — Event listings, top-8 decks, deck viewer
- **US3**: Cards & Avatars — Card browser, avatar browser, detail pages
- **US4**: Content & Interactive — Home, About, Help, Community, Life Counter, Curio Tracking, Fun Stats
- **US5**: Admin — Audit log with admin guards
- **US6**: Deployment — Nginx, CI/CD, production build

---

## Phase 1: Setup (React Project Scaffolding)

**Purpose**: Initialize Vite + React project with Tailwind CSS, configure dev tooling

**Note**: Node 18 requires Tailwind v3 + PostCSS (v4's @tailwindcss/vite needs Node 20+). Adjusted accordingly.

- [X] T001 Create `web-app/frontend/` directory and initialize with package.json
- [X] T002 Install core dependencies: react, react-dom, react-router-dom@6, vite@5, @vitejs/plugin-react@4, tailwindcss@3, postcss, autoprefixer
- [X] T003 Configure Vite in `web-app/frontend/vite.config.js`: dev proxy for `/api`, `/avatar-images`, `/card-images`, `/static`, `/discord`, `/google`, `/logout` → `http://localhost:5000`; `@` path alias → `src/`
- [X] T004 [P] Copy color palette, fonts, spacing, screens from `web-app/tailwind.config.js` into `web-app/frontend/tailwind.config.js`; update `content` paths to `./src/**/*.{js,jsx}`
- [X] T005 [P] Create `web-app/frontend/src/main.jsx` entry point that imports Tailwind CSS and renders `<App />`
- [X] T006 [P] Create `web-app/frontend/index.html` with correct font imports (Almendra, Figtree, Fira Code) and dark background matching current site
- [X] T007 Create `web-app/frontend/src/App.jsx` with React Router `createBrowserRouter` skeleton — all routes defined but pointing to placeholder page components
- [X] T008 [P] Add `.gitignore` in `web-app/frontend/` for `node_modules/`, `dist/`

**Checkpoint**: `npm run dev` starts Vite on :5173, shows placeholder page, proxies `/api/leaderboard` to Flask

---

## Phase 2: Foundational (Flask Backend Changes + API Client + Auth)

**Purpose**: Backend changes and core React infrastructure that ALL pages depend on

**CRITICAL**: No page migration can begin until this phase is complete

### Flask Backend Changes

- [X] T009 Add `FRONTEND_URL` to `web-app/webapp_config.py`: `os.environ.get("FRONTEND_URL", "http://localhost:5173")`
- [X] T010 Add `GET /api/me` endpoint in `web-app/routes/auth.py` returning `{user_id, username, avatar, auth_provider, is_admin}` from session or 401 (per contracts/auth.md)
- [X] T011 Add `GET /api/logout` endpoint in `web-app/routes/auth.py` that clears session and returns `{"ok": true}` (JSON response — React handles navigation)
- [X] T012 [P] Update Discord OAuth callback in `web-app/routes/auth.py` (`discord_callback`): replace `redirect(url_for("pages.home"))` with `redirect(FRONTEND_URL)`
- [X] T013 [P] Update Google OAuth callback in `web-app/routes/auth.py` (`google_callback`): replace `redirect(url_for("pages.home"))` with `redirect(FRONTEND_URL)`
- [X] T014 [P] Add `/api/events` route alias in `web-app/routes/api/events.py` with `GET /events` endpoint
- [X] T015 [P] Add `/api/community` endpoint in `web-app/routes/api/misc.py` returning `{discord_servers, websites}` as JSON

### React API Client

- [X] T016 Create `web-app/frontend/src/api/client.js`: base fetch wrapper with `credentials: 'include'`, JSON parsing, `ApiError` class, and `API_BASE_URL` from `import.meta.env.VITE_API_BASE_URL`
- [X] T017 [P] Create `web-app/frontend/src/api/auth.js`: `getMe()`, `logout()` functions per contracts/auth.md
- [X] T018 [P] Create `web-app/frontend/src/api/leaderboard.js`: `getLeaderboard()`, `getEventLeaderboard()`, `getLimitedLeaderboard()` per contracts/leaderboard.md
- [X] T019 [P] Create `web-app/frontend/src/api/players.js`: `getPlayer(id)`, `getPlayerMatches(id, page)`, `getPlayerAvatarStats(id)` per contracts/players.md
- [X] T020 [P] Create `web-app/frontend/src/api/matches.js`: `getMatches(date)`, `getAvailableDates()` per contracts/matches.md
- [X] T021 [P] Create `web-app/frontend/src/api/events.js`: `getEvents()`, `getEvent(folder)` per contracts/events.md
- [X] T022 [P] Create `web-app/frontend/src/api/decks.js`: `getDeck(deckId)`, `extractDeckId(curiosaUrl)` per contracts/decks.md
- [X] T023 [P] Create `web-app/frontend/src/api/cards.js`: `getAvatars()`, `getAvatar(name)`, `getCards()`, `getCard(name)` for card/avatar API endpoints
- [X] T024 [P] Create `web-app/frontend/src/api/community.js`: `getCommunity()` for community links
- [X] T025 [P] Create `web-app/frontend/src/api/curios.js`: `getCurioEntries()`, `getCurioSets()` for curio tracking

### Auth Context

- [X] T026 Create `web-app/frontend/src/context/AuthContext.jsx`: React Context calling `getMe()` on mount, exposing `{user, loading}` via `useAuth()` hook. `user` is `null` (loading), `false` (unauthenticated), or User object per data-model.md

### UI Primitives

- [X] T027 [P] Create `web-app/frontend/src/components/ui/Spinner.jsx`: loading spinner with Tailwind animation classes
- [X] T028 [P] Create `web-app/frontend/src/components/ui/Button.jsx`: reusable button with variant props (primary, secondary, danger)
- [X] T029 [P] Create `web-app/frontend/src/components/ui/Avatar.jsx`: user/player avatar image with fallback
- [X] T030 [P] Create `web-app/frontend/src/components/ui/Badge.jsx`: small label component for ranks, elements, etc.

### Layout Components

- [X] T031 Create `web-app/frontend/src/components/layout/Nav.jsx`: navigation bar matching current site design — logo, links (Leaderboard, Events, Cards, Community, etc.), auth buttons; conditionally show admin links when `user.is_admin`; mobile hamburger menu
- [X] T032 Create `web-app/frontend/src/components/layout/Footer.jsx`: footer matching current site design with links

### App Shell Integration

- [X] T033 Update `web-app/frontend/src/App.jsx`: wrap routes in `AuthProvider`, add `<Nav />` and `<Footer />` as persistent layout around `<Outlet />`

**Checkpoint**: App shell loads, `/api/me` fires on mount, Nav renders with auth state, Login/Logout works end-to-end through Discord/Google OAuth, all API client modules return data from Flask

---

## Phase 3: US1 — Core Data Pages (Leaderboard, Player, Matches) (Priority: P1) — MVP

**Goal**: Migrate the most-visited pages — leaderboard views, player profiles, and match history

**Independent Test**: Navigate to `/elo`, see leaderboard table; click player → `/player/:id` shows profile with stats; click matches → `/match-history` shows filterable match list

### Shared Components

- [X] T034 [P] [US1] Create `web-app/frontend/src/components/leaderboard/LeaderboardTable.jsx`: sortable table with rank, name, ELO, W/L, win rate columns; clickable rows link to `/player/:id`; reused across all leaderboard views
- [X] T035 [P] [US1] Create `web-app/frontend/src/components/player/PlayerCard.jsx`: player summary card (avatar, name, ELO, rank, W/L record); used on player profile and in match entries

### Leaderboard Pages

- [X] T036 [US1] Create `web-app/frontend/src/pages/Leaderboard.jsx`: tabbed view for lifetime/event/limited/global ELO leaderboards using `LeaderboardTable`; parallel fetch via `Promise.all([getLeaderboard(), getEventLeaderboard(), ...])`
- [X] T037 [P] [US1] Create `web-app/frontend/src/pages/Season.jsx`: season-specific leaderboard at `/season/:seasonId`

### Player Pages

- [X] T038 [US1] Create `web-app/frontend/src/pages/Player.jsx`: full player profile at `/player/:playerId` — header with `PlayerCard`, avatar stats breakdown, recent match list; parallel fetch for profile + avatar stats
- [X] T039 [P] [US1] Create `web-app/frontend/src/pages/DeckStats.jsx`: player deck statistics at `/deck-stats/:playerId`

### Match Pages

- [X] T040 [US1] Create `web-app/frontend/src/pages/Matches.jsx`: match history at `/match-history` with date picker using available dates API; clickable player names link to profiles
- [X] T041 [P] [US1] Create `web-app/frontend/src/pages/DeckSnapshot.jsx`: per-match deck snapshot at `/deck-snapshot/:matchId/:playerId`

### Route Registration

- [X] T042 [US1] Register all Phase 3 routes in `web-app/frontend/src/App.jsx`: `/elo`, `/elo/limited`, `/elo/global`, `/elo/server/:serverId`, `/season/:seasonId`, `/player/:playerId`, `/match-history`, `/deck-stats/:playerId`, `/deck-snapshot/:matchId/:playerId`

**Checkpoint**: Full leaderboard → player → match flow works. Can browse ELO rankings, click into player profiles, view match history with date filtering.

---

## Phase 4: US2 — Events & Decks (Priority: P2)

**Goal**: Migrate event listings, top-8 deck views, and deck detail pages with lazy-loaded DeckViewer

**Independent Test**: Navigate to `/top-8`, see event list with star ratings; click event → `/top-8/:folder` shows top 8 decks; expand deck → card grid renders

### Shared Components

- [X] T043 [P] [US2] Create `web-app/frontend/src/components/deck/DeckViewer.jsx` (lazy-loaded): renders deck card grid grouped by type/element, card images from `/card-images/`, avatar header; export as default for `React.lazy()` compatibility

### Event Pages

- [X] T044 [US2] Create `web-app/frontend/src/pages/Events.jsx`: event list at `/top-8` — grid of event cards with star ratings, display names, deck counts; links to event detail
- [X] T045 [US2] Create `web-app/frontend/src/pages/EventDetail.jsx`: event detail at `/top-8/:folder` — top 8 deck list with player names, placements, expandable deck views using lazy `DeckViewer` via `<Suspense>`
- [X] T046 [P] [US2] Create `web-app/frontend/src/pages/Stats.jsx`: event stats overview at `/stats`
- [X] T047 [P] [US2] Create `web-app/frontend/src/pages/StatsEvent.jsx`: per-event stats at `/stats/:folder`

### Deck Pages

- [X] T048 [US2] Create `web-app/frontend/src/pages/DeckDetail.jsx`: standalone deck view at `/deck-rec/:deckId` using lazy `DeckViewer`
- [X] T049 [P] [US2] Create `web-app/frontend/src/pages/DeckRecommendations.jsx`: deck recommendations at `/deck-rec`

### Route Registration

- [X] T050 [US2] Register all Phase 4 routes in `web-app/frontend/src/App.jsx`: `/top-8`, `/top-8/:folder`, `/stats`, `/stats/:folder`, `/deck-rec`, `/deck-rec/:deckId`

**Checkpoint**: Full events → deck viewer flow works. Event cards display with star ratings, top 8 decks render with lazy-loaded DeckViewer component.

---

## Phase 5: US3 — Cards & Avatars (Priority: P3)

**Goal**: Migrate card browser, avatar browser, and detail pages

**Independent Test**: Navigate to `/avatars`, see avatar grid; click avatar → `/avatar/:name` shows stats; same for `/cards`

- [X] T051 [P] [US3] Create `web-app/frontend/src/pages/Avatars.jsx`: avatar browser at `/avatars` — grid of avatar cards with images, names, win rates
- [X] T052 [P] [US3] Create `web-app/frontend/src/pages/AvatarDetail.jsx`: avatar detail at `/avatar/:name` — avatar image, element, aggregated win/loss stats, top players using that avatar
- [X] T053 [P] [US3] Create `web-app/frontend/src/pages/Cards.jsx`: card browser at `/cards` — searchable/filterable card grid
- [X] T054 [P] [US3] Create `web-app/frontend/src/pages/CardDetail.jsx`: card detail at `/card/:name` — card image, usage stats, decks featuring this card
- [X] T055 [P] [US3] Create `web-app/frontend/src/pages/Elements.jsx`: elements overview at `/elements`
- [X] T056 [P] [US3] Create `web-app/frontend/src/pages/LivePopularCards.jsx`: live popular cards at `/live-popular-cards`
- [X] T057 [US3] Register all Phase 5 routes in `web-app/frontend/src/App.jsx`: `/avatars`, `/avatar/:name`, `/cards`, `/card/:name`, `/elements`, `/live-popular-cards`

**Checkpoint**: Card and avatar browsing fully functional. Can search, filter, and view detailed stats.

---

## Phase 6: US4 — Content & Interactive Pages (Priority: P4)

**Goal**: Migrate static content pages, community, life counter, curio tracking, and fun stats

**Independent Test**: Navigate to `/about`, `/help`, `/community`, `/life-counter` — all render correctly with shared layout

### Static Content Pages (lightweight, hardcoded)

- [X] T058 [P] [US4] Create `web-app/frontend/src/pages/Home.jsx`: landing page at `/` — recent event banner, community highlights
- [X] T059 [P] [US4] Create `web-app/frontend/src/pages/About.jsx`: about page at `/about` — static content matching current design
- [X] T060 [P] [US4] Create `web-app/frontend/src/pages/Help.jsx`: help/documentation at `/help` — static content matching current design
- [X] T061 [P] [US4] Create `web-app/frontend/src/pages/Privacy.jsx`: privacy policy at `/privacy` — static content
- [X] T062 [P] [US4] Create `web-app/frontend/src/pages/Terms.jsx`: terms of service at `/terms` — static content
- [X] T063 [P] [US4] Create `web-app/frontend/src/pages/DeckHelp.jsx`: deck help at `/deck-help` — static content

### Interactive Pages

- [X] T064 [US4] Create `web-app/frontend/src/pages/Community.jsx`: community page at `/community` — fetches community links via `api/community.js`, renders Discord server cards + website cards
- [X] T065 [US4] Create `web-app/frontend/src/pages/LifeCounter.jsx`: life counter at `/life-counter` — rebuilt as React component with `useState` for life totals; uses `useAuth()` for user context instead of template-injected session data
- [X] T066 [US4] Create `web-app/frontend/src/pages/CurioTracking.jsx` (lazy-loaded via `React.lazy()`): curio tracking at `/curio-tracking` — fetches entries/sets via `api/curios.js`, renders filterable curio table with images
- [X] T067 [P] [US4] Create `web-app/frontend/src/pages/FunStats.jsx`: fun stats at `/fun-stats` — fetches fun stats data, renders stat cards
- [X] T068 [P] [US4] Create `web-app/frontend/src/pages/FartLeaderboard.jsx`: fart leaderboard at `/secret-fart-leaderboard`
- [X] T069 [US4] Create `web-app/frontend/src/pages/Login.jsx`: login page at `/login` — Discord and Google OAuth buttons linking to `/discord` and `/google` Flask routes

### Route Registration

- [X] T070 [US4] Register all Phase 6 routes in `web-app/frontend/src/App.jsx`: `/`, `/about`, `/help`, `/privacy`, `/terms`, `/deck-help`, `/community`, `/life-counter`, `/curio-tracking` (lazy), `/fun-stats`, `/secret-fart-leaderboard`, `/login`

**Checkpoint**: All content pages render correctly with shared layout. Life counter is fully interactive. Curio tracking loads lazily.

---

## Phase 7: US5 — Admin Pages (Priority: P5)

**Goal**: Migrate admin pages with authorization guards

**Independent Test**: Non-admin user navigates to `/admin/audit-log` → redirected to `/`. Admin user sees full audit log.

- [X] T071 [US5] Create `web-app/frontend/src/components/layout/AdminGuard.jsx`: wrapper component that checks `user.is_admin` from `useAuth()`, renders children if admin or redirects to `/`
- [X] T072 [US5] Create `web-app/frontend/src/pages/admin/AuditLog.jsx`: admin audit log at `/admin/audit-log` — fetches audit data from existing admin API endpoint, renders log table
- [X] T073 [US5] Register admin routes in `web-app/frontend/src/App.jsx`: `/admin/audit-log` wrapped in `AdminGuard`

**Checkpoint**: Admin pages accessible only to admin users. API endpoints still enforce `@require_admin` server-side as defense-in-depth.

---

## Phase 8: US6 — Deployment & CI/CD (Priority: P6)

**Goal**: Production deployment — Nginx catch-all, CI/CD pipeline, Node.js on server

**Independent Test**: Push to `main`, deploy workflow runs, site serves React SPA for all non-API routes, API endpoints still work, OAuth login works end-to-end

- [X] T074 [US6] Create updated Nginx config at `web-app/nginx/summit-web-react.conf`: add `location /` catch-all serving `frontend/dist/index.html` via `try_files $uri $uri/ /index.html`; keep existing `/api/`, `/avatar-images/`, `/card-images/`, `/static/` proxy/alias blocks above the catch-all
- [X] T075 [US6] Update `.github/workflows/deploy-web.yml`: add `cd web-app/frontend && npm ci && npm run build` step before service restart; set `FRONTEND_URL` env var for production
- [X] T076 [US6] Add `web-app/frontend/` to deploy trigger paths in `.github/workflows/deploy-web.yml` alongside existing `web-app/**`
- [X] T077 [P] [US6] Document Node.js 20 LTS installation instructions in `web-app/DEPLOYMENT.md` as a one-time server setup prerequisite
- [X] T078 [P] [US6] Create `web-app/frontend/README.md` per quickstart.md: local dev setup (Flask + Vite), build instructions, project structure overview, auth flow, common gotchas

**Checkpoint**: Full production deployment. React SPA serves all pages, Flask API handles data, Nginx routes correctly, OAuth works end-to-end.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup, visual verification, and performance checks

- [X] T079 Verify all React Router `<Link>` elements in Nav, Footer, and inter-page navigation match route definitions in `App.jsx` — fix any broken links
- [X] T080 [P] Add `<title>` per page using `document.title` in `useEffect` or a shared `usePageTitle(title)` hook in `web-app/frontend/src/hooks/usePageTitle.js`
- [X] T081 [P] Create 404 Not Found page at `web-app/frontend/src/pages/NotFound.jsx` and add catch-all `path="*"` route in `App.jsx`
- [X] T082 [P] Add loading states to all data-fetching pages: show `<Spinner />` while API calls are in flight
- [X] T083 [P] Add error states to all data-fetching pages: show user-friendly error message when API calls fail
- [X] T084 Verify `React.lazy()` + `<Suspense>` is correctly applied to `DeckViewer` and `CurioTracking` — run `npm run build` and confirm separate chunks in output
- [X] T085 Run `npm run build` and verify initial bundle size is under 200KB gzipped
- [X] T086 Visual comparison: side-by-side check of each React page against the Jinja2 original — ensure color palette, fonts, spacing, and layout match

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all page migrations
- **Phases 3–7 (US1–US5)**: All depend on Phase 2 completion
  - **Phase 3 (US1)**: Can start immediately after Phase 2 — **MVP**
  - **Phase 4 (US2)**: Can run in parallel with Phase 3
  - **Phase 5 (US3)**: Can run in parallel with Phases 3–4
  - **Phase 6 (US4)**: Can run in parallel with Phases 3–5
  - **Phase 7 (US5)**: Can run in parallel with Phases 3–6
- **Phase 8 (Deployment)**: Nginx/CI config can start after Phase 2; full deploy after all pages complete
- **Phase 9 (Polish)**: Depends on all page phases (3–7) being complete

### Within Each Phase

- API client modules (T017–T025) before pages that use them
- Shared components (LeaderboardTable, PlayerCard, DeckViewer) before pages that compose them
- Route registration after all page components in that phase exist
- [P] tasks within a phase can run in parallel

### Parallel Opportunities

```
After Phase 2 completes:
  ├── Phase 3 (US1): Leaderboard + Player + Matches     ← MVP
  ├── Phase 4 (US2): Events + Decks                     ← parallel
  ├── Phase 5 (US3): Cards + Avatars                    ← parallel
  ├── Phase 6 (US4): Content + Interactive               ← parallel
  └── Phase 7 (US5): Admin                               ← parallel
```

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Flask backend changes — different endpoints, run in parallel:
T012: Update Discord callback in routes/auth.py
T013: Update Google callback in routes/auth.py   # same file as T012, run sequentially
T014: Add /api/events alias
T015: Add /api/community endpoint

# API client modules — all different files, run in parallel:
T017: api/auth.js
T018: api/leaderboard.js
T019: api/players.js
T020: api/matches.js
T021: api/events.js
T022: api/decks.js
T023: api/cards.js
T024: api/community.js
T025: api/curios.js

# UI primitives — all different files, run in parallel:
T027: ui/Spinner.jsx
T028: ui/Button.jsx
T029: ui/Avatar.jsx
T030: ui/Badge.jsx
```

---

## Parallel Example: Phase 3 (US1 - MVP)

```bash
# Shared components — different files, run in parallel:
T034: LeaderboardTable.jsx
T035: PlayerCard.jsx

# Pages — different files, run in parallel (after shared components):
T036: Leaderboard.jsx
T037: Season.jsx
T038: Player.jsx
T039: DeckStats.jsx
T040: Matches.jsx
T041: DeckSnapshot.jsx
```

---

## Implementation Strategy

### MVP First (Phase 1 + 2 + 3 Only)

1. Complete Phase 1: React scaffolding with Vite + Tailwind
2. Complete Phase 2: Flask `/api/me` + API client + AuthContext + Layout
3. Complete Phase 3: Leaderboard + Player + Matches
4. **STOP and VALIDATE**: Core user journey works end-to-end
5. Can deploy behind staging URL for verification

### Incremental Delivery

1. Setup + Foundational → App shell with auth working
2. Add US1 (Leaderboard/Player/Matches) → Most-used pages live (**MVP**)
3. Add US2 (Events/Decks) → Event browsing + deck viewer
4. Add US3 (Cards/Avatars) → Card browser
5. Add US4 (Content/Interactive) → All remaining pages
6. Add US5 (Admin) → Admin panel
7. Deploy to production → Full migration complete
8. Polish → Visual parity, performance, error handling

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story phase is independently deployable (pages just won't be linked in Nav until registered)
- Jinja2 templates remain running in parallel — no removal until React is verified in production
- All fetch calls go through `api/client.js` — never raw `fetch()` in pages
- No barrel `index.js` files — all imports are direct file paths (e.g., `import PlayerCard from '@/components/player/PlayerCard'`)
- Heavy components (DeckViewer, CurioTracking) must use `React.lazy()` + `<Suspense>`
- The `losser_id` / `losser_display_name` column typo is intentional — match the existing DB schema exactly
- Commit after each task or logical group
