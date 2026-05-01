# Implementation Plan: Flask/Jinja2 → React SPA Migration

**Branch**: `main` | **Date**: 2026-04-30 | **Spec**: user-provided via /speckit.plan
**Input**: Inline feature specification from /speckit.plan invocation

## Summary

Migrate the Summit Discord Bot web app from Jinja2 server-side rendering to a React SPA (Vite + React 18 + React Router 6 + Tailwind CSS v4) with Flask serving as a pure JSON API backend. All existing Flask API routes under `/api/**` remain unchanged. A new `GET /api/me` endpoint exposes session user data to the SPA. Auth flows (Discord + Google OAuth) continue through Flask, with callbacks redirecting to the React app root URL. The React app lives at `web-app/frontend/` and builds to `dist/`, which Nginx serves as a catch-all for non-API routes. Discord bot infrastructure is completely untouched.

## Technical Context

**Language/Version**: Python 3.11 (Flask backend, unchanged) / JavaScript ES2022 (React frontend, no TypeScript)
**Primary Dependencies**: React 18, React Router 6, Vite 5, Tailwind CSS v4 (@tailwindcss/vite plugin), flask-cors (dev only)
**Storage**: SQLite (unchanged) — no schema changes required
**Testing**: pytest (backend, unchanged), Vitest + React Testing Library (frontend)
**Target Platform**: Linux VPS (Linode), systemd, Nginx, Cloudflare CDN
**Project Type**: Web application — SPA frontend + Flask REST API backend
**Performance Goals**: Initial JS bundle <200KB gzipped; lazy-load DeckViewer + CurioTracking pages; no sequential API request waterfalls (Promise.all in api layer)
**Constraints**: Flask session cookie (SameSite=Lax, Secure, HttpOnly — already configured) must be sent with all API calls via `credentials: 'include'`; no JWT; no SSR; no TypeScript
**Scale/Scope**: ~15 pages, ~20 API modules, single VPS deployment

## Constitution Check

*The project constitution is unpopulated (template placeholders only) — no project-specific architectural gates are defined.*

**Result**: No violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── auth.md
│   ├── leaderboard.md
│   ├── players.md
│   ├── matches.md
│   ├── events.md
│   └── decks.md
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code Layout

```text
web-app/
├── app.py                        # Add /api/me + /api/logout; remove pages blueprint when ready
├── routes/
│   ├── api/                      # All /api/** endpoints (unchanged)
│   └── auth.py                   # Change callback redirects → React app root URL
├── services/                     # Unchanged
├── repositories/                 # Unchanged
└── frontend/                     # NEW: React SPA
    ├── index.html
    ├── vite.config.js             # Proxy /api/*, /avatar-images/*, /card-images/* → Flask :5000
    ├── tailwind.config.js         # Color palette + custom design tokens
    ├── postcss.config.js
    ├── package.json
    ├── README.md                  # Local dev setup (Flask + Vite)
    └── src/
        ├── main.jsx               # App entry point
        ├── App.jsx                # React Router route definitions
        ├── api/                   # Centralized fetch client — only place with URLs
        │   ├── client.js          # Base fetch (credentials: include, error handling)
        │   ├── auth.js            # GET /api/me, GET /logout
        │   ├── leaderboard.js     # GET /api/leaderboard, /api/leaderboard/event, etc.
        │   ├── players.js         # GET /api/players/:id, /api/players/:id/matches
        │   ├── matches.js         # GET /api/match-history
        │   ├── events.js          # GET /api/events (pages.py), /api/events/:id/decks
        │   └── decks.js           # GET /api/cards/:id
        ├── context/
        │   └── AuthContext.jsx    # Global user state via /api/me; provides useAuth()
        ├── components/
        │   ├── layout/
        │   │   ├── Nav.jsx
        │   │   └── Footer.jsx
        │   ├── player/
        │   │   └── PlayerCard.jsx
        │   ├── deck/
        │   │   └── DeckViewer.jsx  # lazy-loaded via React.lazy()
        │   ├── leaderboard/
        │   │   └── LeaderboardTable.jsx
        │   └── ui/
        │       ├── Button.jsx
        │       ├── Avatar.jsx
        │       ├── Badge.jsx
        │       └── Spinner.jsx
        └── pages/                  # Thin page components — fetch via api/, compose components
            ├── Home.jsx
            ├── Leaderboard.jsx
            ├── Player.jsx
            ├── Matches.jsx
            ├── Events.jsx
            ├── EventDetail.jsx
            ├── DeckDetail.jsx      # lazy DeckViewer via Suspense
            ├── Community.jsx
            ├── CurioTracking.jsx   # lazy-loaded
            ├── Help.jsx            # lightweight hardcoded content
            ├── LifeCounter.jsx     # rebuilt as React component
            ├── About.jsx           # lightweight hardcoded content
            ├── Privacy.jsx         # lightweight hardcoded content
            ├── Terms.jsx           # lightweight hardcoded content
            ├── Login.jsx
            └── admin/
                └── AuditLog.jsx    # admin-only, guarded by is_admin from AuthContext
```

**Structure Decision**: Web application layout (Option 2). Flask backend unchanged at `web-app/`; new React SPA at `web-app/frontend/`. Jinja2 templates and `routes/pages.py` remain registered in Flask during migration (parallel operation) — Nginx catch-all serves React for end users while Jinja2 stays as fallback. Nginx proxies `/api/**`, `/avatar-images/**`, `/card-images/**` to Gunicorn. Flask route `/api/games` renamed to `/api/events` (keep `/api/games` as deprecated alias). Admin pages migrated to React with server-side admin checks via `is_admin` in `/api/me`. No barrel `index.js` files — all imports are direct file paths.

## Complexity Tracking

*No constitution violations to justify.*
