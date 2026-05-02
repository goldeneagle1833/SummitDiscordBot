# Summit Web App

Flask REST API + React frontend for the Summit Sorcery: Contested Realm community. Provides leaderboards, player profiles, match history, tournament decks, card/avatar stats, and admin tools.

## Architecture

The web app has two parts:

- **Flask** — REST API only (`/api/*`), OAuth (`/auth/*`), and static file serving. No HTML rendering.
- **React (Vite)** — SPA that handles all page rendering. In production, Nginx serves the built `frontend/dist/` directly.

In development, Vite runs on port 5173 and proxies API calls to Flask on port 5000.

---

## Local Dev Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm

### 1. Flask API

```bash
cd web-app
pip install -r requirements.txt
```

Seed test databases (creates sample data in `../discord-bot/`):
```bash
python scripts/seed_databases.py
```

Run Flask:
```bash
python app.py   # http://localhost:5000
```

For OAuth login, add to `../discord-bot/.env`:
```env
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=http://localhost:5173/auth/discord/callback
SECRET_KEY=any_random_string
```

### 2. React Frontend

```bash
cd web-app/frontend
npm install
npm run dev   # http://localhost:5173
```

Vite proxies `/api`, `/auth`, `/static`, `/avatar-images`, `/card-images` to `http://localhost:5000`. Both Flask and Vite must be running for the full app to work.

### Build for Production

```bash
cd web-app/frontend
npm run build   # Output goes to frontend/dist/
```

---

## Project Structure

```
web-app/
├── app.py                      # Flask app factory, startup migrations
├── webapp_config.py            # Config (DB paths, OAuth, admin IDs)
├── gunicorn_config.py          # Production WSGI config
├── requirements.txt
│
├── routes/
│   ├── auth.py                 # Discord & Google OAuth flows
│   └── api/                    # All REST endpoints (return JSON only)
│       ├── admin.py            # Admin operations, audit log
│       ├── avatars.py          # Avatar statistics
│       ├── cards.py            # Card database & search
│       ├── curios.py           # Curio tracking CRUD
│       ├── deck_recommendations.py
│       ├── events.py           # Tournament events
│       ├── external_matches.py # External match reporting
│       ├── fun_stats.py        # Fart leaderboard
│       ├── games.py            # Game statistics
│       ├── leaderboard.py      # 7 leaderboard types
│       ├── limited.py          # Limited arena
│       ├── match_reporting.py  # Match confirmation workflow
│       ├── matches.py          # Match history
│       ├── misc.py             # Health check
│       ├── players.py          # Player profiles & stats
│       ├── seasons.py          # Custom season management
│       └── streamers.py        # Active streamer detection
│
├── services/                   # Business logic
│   ├── admin.py
│   ├── curiosa.py              # Curiosa API integration
│   ├── deck_similarity.py
│   ├── external_match.py
│   ├── leaderboard.py          # Leaderboard calculations
│   ├── limited_service.py
│   ├── match.py
│   ├── match_confirmation.py   # 48-hour confirmation workflow
│   ├── paper_elo.py
│   ├── pilots.py               # Feature flags
│   ├── player.py
│   ├── seasons.py
│   └── youtube.py
│
├── repositories/               # SQLite data access
│   ├── analytics.py
│   ├── audit.py
│   ├── avatar_image_settings.py
│   ├── community.py
│   ├── curios.py
│   ├── deck_rec_repo.py
│   ├── elo.py
│   ├── events.py               # Reads JSON files from top-8-decks-by-event/
│   ├── fart.py
│   ├── limited_repo.py
│   ├── match_confirmation.py
│   ├── matches.py
│   ├── seasons.py
│   └── user_profiles.py
│
├── utils/
│   ├── auth.py                 # Decorators: require_auth, require_api_key, is_admin
│   ├── api_auth.py             # Draft Sorcery API key validation
│   ├── formatting.py           # Event name formatting, pseudonyms
│   └── version.py
│
├── migrations/                 # DB migrations (auto-run on Flask startup)
├── scripts/
│   └── seed_databases.py       # Create local test databases with sample data
│
├── frontend/                   # React + Vite SPA
│   ├── src/
│   │   ├── App.jsx             # Router — all routes defined here
│   │   ├── pages/              # One component per route
│   │   ├── components/         # Shared components (layout, player, deck, admin)
│   │   ├── api/                # Typed fetch wrappers for each API area
│   │   └── context/            # AuthContext
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── package.json
│
├── static/
│   ├── images/
│   │   ├── favicon.png         # Used by React index.html
│   │   └── elements/           # Element SVGs/PNGs used by MatchHistoryTable
│   └── uploads/                # User-uploaded content (curio images, banners)
│
├── templates/
│   └── avatar_imgs/            # Avatar image files (served by Nginx directly)
│
├── top-8-decks-by-event/       # Tournament deck JSON files (40+ events)
├── card_images/                # Card image cache
├── nginx/                      # Nginx configs (standard + Cloudflare)
└── systemd/                    # systemd service file
```

---

## Databases

The web app shares SQLite databases with the Discord bot (paths default to `../discord-bot/`):

| Database | Key Tables |
|---|---|
| `elo.db` | `overall_standings`, `events`, `event_standings_archive`, `paper_standings`, `limited_elo` |
| `match_records.db` | `match_records`, `match_reports_web`, `match_confirmations`, `user_profiles`, `seasons`, `admin_audit_log`, `limited_arena_runs` |
| `fart_scores.db` | `fart_scores` |
| `community.db` | `discord_servers`, `youtube_channels`, `websites`, `curio_sets`, `curio_entries` |

Override paths via environment variables:
```env
ELO_DB_PATH=/path/to/elo.db
MATCH_RECORDS_DB_PATH=/path/to/match_records.db
FART_SCORES_DB_PATH=/path/to/fart_scores.db
COMMUNITY_DB_PATH=/path/to/community.db
```

---

## API Overview

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for full details.

**Auth:** Session cookie (OAuth login) or `X-API-Key` header.

Key endpoints:

| Endpoint | Description |
|---|---|
| `GET /api/status` | Health check |
| `GET /api/leaderboard` | Lifetime ELO rankings |
| `GET /api/players/<id>` | Player profile & stats |
| `GET /api/match-history` | Match history |
| `GET /api/events` | Tournament events |
| `GET /api/cards` | Card database |
| `GET /api/avatars` | Avatar statistics |
| `POST /api/match-report/submit` | Submit match (auth required) |

---

## Configuration

All optional for local development:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | Auto-generated | Flask session key (required in production) |
| `DISCORD_CLIENT_ID` | None | Discord OAuth |
| `DISCORD_CLIENT_SECRET` | None | Discord OAuth |
| `GOOGLE_CLIENT_ID` | None | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | None | Google OAuth |
| `API_KEYS` | Empty | Comma-separated API keys |
| `ADMIN_IDS` | Empty | Comma-separated admin Discord/Google IDs |
| `CURIO_EDITOR_IDS` | Empty | Comma-separated curio editor IDs |

---

## Production Deployment

```bash
# Build React
cd web-app/frontend && npm run build

# Run Flask with Gunicorn
cd web-app && gunicorn -c gunicorn_config.py app:app
```

Nginx serves React's `frontend/dist/` for all page routes and proxies only `/api/`, `/auth/`, `/static/` to Flask. See [nginx/summit-web-cloudflare.conf](nginx/summit-web-cloudflare.conf) and [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Troubleshooting

**"Database file not found"** — Run `python scripts/seed_databases.py` from the `web-app/` directory.

**OAuth "Invalid Redirect URI"** — Add `http://localhost:5173/auth/discord/callback` to your Discord app's redirect URIs.

**API returns empty data** — Check databases exist. Run `python scripts/seed_databases.py`.

**React changes not showing in production** — Run `npm run build` and redeploy.
