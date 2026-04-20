# Summit Web App

A Flask web application providing leaderboards, player stats, match history, deck viewing, curio tracking, and a REST API for the Summit Sorcery: Contested Realm community.

## Features

- **Leaderboards** - ELO rankings: lifetime, event, paper, online, combined, and limited arena
- **Player Profiles** - Detailed stats, match history, win/loss by source, deck usage
- **Match Reporting** - Web-based match reporting with 48-hour opponent confirmation workflow
- **Deck Browser** - Top 8 decks from 40+ tournaments (Gen Con, SCG Con, Sorcery Con, etc.)
- **Card & Avatar Stats** - Metagame analytics, card usage, avatar popularity
- **Custom Seasons** - User-created mini-leaderboards with separate ELO tracking
- **Limited Arena** - Separate ELO and arena run tracking for limited format
- **Curio Tracking** - Community-driven booster box pull tracking with image uploads
- **REST API** - Comprehensive endpoints for all data
- **Multi-Provider OAuth** - Discord and Google authentication
- **Admin Tools** - Match deletion, ELO management, full audit logging

## Prerequisites

- **Python 3.10+** (3.12+ recommended, uses `X | Y` union type syntax)
- **pip** (Python package installer)
- **Git** (for cloning the repository)

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/yourusername/SummitDiscordBot.git
cd SummitDiscordBot/web-app
```

### 2. Create Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create Test Databases

The web app reads from SQLite databases normally created by the Discord bot. For local development without the bot, run the seed script to create databases with sample data:

```bash
python scripts/seed_databases.py
```

This creates all four databases in `../discord-bot/` with the correct schemas and sample data:
- `elo.db` - Player ELO ratings, events, paper standings, limited ELO
- `match_records.db` - Match history, match confirmations, user profiles, seasons, audit log
- `fart_scores.db` - Fart game scores
- `community.db` - Community links, curio tracking

If you already have databases from the Discord bot, the seed script will skip them (no data is overwritten).

### 5. Set Up Environment Variables (Optional)

For basic local development, no `.env` file is needed. The app auto-generates a session key and runs without OAuth.

For full functionality, create `../discord-bot/.env`:

```env
# Discord OAuth (for login)
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=http://localhost:5000/auth/discord/callback

# Google OAuth (alternative login)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback

# Flask session key (auto-generated in dev if not set)
SECRET_KEY=your_secret_key_here

# API keys for external integrations (comma-separated)
API_KEYS=key1,key2

# Draft Sorcery API key for limited arena
DRAFT_SORCERY_API_KEY=your_key
```

### 6. Run the Application

```bash
python app.py
```

Open http://localhost:5000. Key pages to verify:
- http://localhost:5000/leaderboard - ELO leaderboard
- http://localhost:5000/match-history - Match history
- http://localhost:5000/api/status - API health check

## Project Structure

```
web-app/
├── app.py                          # Application factory, Flask setup, migrations
├── webapp_config.py                # Configuration (DB paths, OAuth, admins, events)
├── gunicorn_config.py              # Production WSGI config (Unix socket, workers)
├── requirements.txt                # Dependencies
├── scripts/
│   └── seed_databases.py           # Create test databases for local development
│
├── routes/                         # HTTP handlers
│   ├── __init__.py                 # Route registration
│   ├── pages.py                    # 50+ HTML page routes
│   ├── auth.py                     # Discord & Google OAuth flows
│   └── api/                        # REST API endpoints
│       ├── admin.py                # Admin operations, audit log
│       ├── avatars.py              # Avatar statistics
│       ├── cards.py                # Card database & search
│       ├── curios.py               # Curio tracking CRUD
│       ├── events.py               # Tournament events & archives
│       ├── external_matches.py     # External match reporting
│       ├── fun_stats.py            # Fart leaderboard
│       ├── games.py                # Game statistics
│       ├── leaderboard.py          # 7 leaderboard types
│       ├── limited.py              # Limited arena endpoints
│       ├── match_reporting.py      # Match confirmation workflow
│       ├── matches.py              # Match history
│       ├── misc.py                 # Health check, debug
│       ├── players.py              # Player profiles & stats
│       ├── seasons.py              # Custom season management
│       └── streamers.py            # Active streamer detection
│
├── services/                       # Business logic
│   ├── admin.py                    # Admin operations
│   ├── curiosa.py                  # Curiosa API integration
│   ├── external_match.py           # External match processing
│   ├── leaderboard.py              # Leaderboard calculations (7 types)
│   ├── limited_service.py          # Limited arena logic
│   ├── match.py                    # Match processing
│   ├── match_confirmation.py       # 48-hour confirmation workflow
│   ├── paper_elo.py                # Paper-only ELO tracking
│   ├── player.py                   # Player data aggregation
│   ├── seasons.py                  # Season management
│   └── youtube.py                  # YouTube API integration
│
├── repositories/                   # Data access (SQLite)
│   ├── audit.py                    # Admin audit log (match_records.db)
│   ├── community.py                # Community links (community.db)
│   ├── curios.py                   # Curio tracking (community.db)
│   ├── elo.py                      # ELO standings, events, paper (elo.db)
│   ├── events.py                   # Tournament decks from JSON files
│   ├── fart.py                     # Fart scores (fart_scores.db)
│   ├── limited_repo.py             # Limited arena tables (match_records.db + elo.db)
│   ├── match_confirmation.py       # Match confirmations (match_records.db)
│   ├── matches.py                  # Match history queries (match_records.db)
│   ├── seasons.py                  # Season tables (match_records.db)
│   └── user_profiles.py            # OAuth profiles (match_records.db)
│
├── utils/                          # Shared utilities
│   ├── auth.py                     # Auth decorators: require_auth, require_api_key, is_admin
│   ├── api_auth.py                 # Draft Sorcery API key validation
│   ├── formatting.py               # Event name formatting, pseudonyms
│   └── version.py                  # App version tracking
│
├── templates/                      # Jinja2 templates
│   ├── base.html                   # Master template
│   ├── components/                 # Navbar, footer, streaming banner
│   ├── errors/                     # 404, 500 pages
│   └── pages/                      # 30+ page templates
│
├── static/                         # CSS, JS, uploads
│   ├── css/
│   │   ├── base/                   # layout, reset, typography, variables
│   │   ├── components/             # 15+ component stylesheets
│   │   ├── pages/                  # 30+ page-specific styles
│   │   ├── utilities/              # colors, flexbox, spacing, visibility
│   │   └── tailwind.output.css     # Tailwind CSS output
│   ├── js/
│   │   ├── core/main.js            # App initialization
│   │   ├── components/             # Navbar, leaderboard, chat, deck-viewer
│   │   └── pages/                  # 20+ page-specific scripts
│   └── uploads/curios/             # Curio image uploads
│
├── top-8-decks-by-event/           # Tournament deck JSON files (40+ events)
├── card_images/                    # Card image cache
├── migrations/                     # Database migration scripts
├── systemd/                        # systemd service file
└── nginx/                          # Nginx configs (standard + Cloudflare)
```

## Databases

The web app uses 4 SQLite databases (default paths relative to `../discord-bot/`):

| Database | Config Variable | Key Tables |
|----------|----------------|------------|
| `elo.db` | `ELO_DB_PATH` | `overall_standings`, `events`, `event_standings_archive`, `paper_standings`, `limited_elo` |
| `match_records.db` | `MATCH_RECORDS_DB_PATH` | `match_records`, `match_records_archive`, `match_reports_web`, `match_confirmations`, `user_profiles`, `seasons`, `season_members`, `season_match_elo`, `limited_arena_runs`, `limited_match_records`, `admin_audit_log` |
| `fart_scores.db` | `FART_SCORES_DB_PATH` | `fart_scores` |
| `community.db` | `COMMUNITY_DB_PATH` | `discord_servers`, `youtube_channels`, `websites`, `curio_sets`, `curio_entries` |

Override paths via environment variables:
```env
ELO_DB_PATH=/path/to/elo.db
MATCH_RECORDS_DB_PATH=/path/to/match_records.db
FART_SCORES_DB_PATH=/path/to/fart_scores.db
COMMUNITY_DB_PATH=/path/to/community.db
```

## API Overview

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for full details.

**Key Endpoints:**

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Health check (no auth) |
| `GET /api/leaderboard` | Lifetime ELO rankings |
| `GET /api/leaderboard/event` | Current event ELO |
| `GET /api/leaderboard/combined` | Lifetime + event |
| `GET /api/leaderboard/paper` | Paper-only ELO |
| `GET /api/players/<id>` | Player profile & stats |
| `GET /api/players/<id>/matches` | Player match history |
| `GET /api/match-history` | Match history (date filter) |
| `GET /api/cards` | Card database |
| `GET /api/avatars` | Avatar statistics |
| `GET /api/events` | Tournament events |
| `GET /api/seasons` | Custom seasons |
| `GET /api/limited/leaderboard` | Limited arena ELO |
| `POST /api/match-report/submit` | Submit match (auth required) |

**Authentication:** Session (OAuth login) or API key (`X-API-Key` header).

## Configuration

### Environment Variables

All optional for local development:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | Auto-generated | Flask session key (required in production) |
| `DISCORD_CLIENT_ID` | None | Discord OAuth |
| `DISCORD_CLIENT_SECRET` | None | Discord OAuth |
| `GOOGLE_CLIENT_ID` | None | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | None | Google OAuth |
| `API_KEYS` | Empty | Comma-separated API keys |
| `DRAFT_SORCERY_API_KEY` | Empty | Limited arena API key |
| `ADMIN_IDS` | Empty | Comma-separated admin Discord/Google IDs |
| `CURIO_EDITOR_IDS` | Empty | Comma-separated curio editor IDs |
| `ELO_DB_PATH` | `../discord-bot/elo.db` | ELO database path |
| `MATCH_RECORDS_DB_PATH` | `../discord-bot/match_records.db` | Match database path |
| `FART_SCORES_DB_PATH` | `../discord-bot/fart_scores.db` | Fart database path |
| `COMMUNITY_DB_PATH` | `../discord-bot/community.db` | Community database path |

### Admin Access

Admin and curio editor IDs are configured via `ADMIN_IDS` and `CURIO_EDITOR_IDS` environment variables (comma-separated). Admins can delete matches, reset ELO, rename players, and view the audit log. Requests from localhost are also treated as admin.

## Production Deployment

### Gunicorn

```bash
gunicorn -c gunicorn_config.py app:app
```

Uses Unix socket (`/tmp/summit-web.sock`), `cpu_count * 2 + 1` workers, 120s timeout.

### systemd

```bash
sudo cp systemd/summit-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now summit-web
```

### Nginx

See [nginx/summit-web.conf](nginx/summit-web.conf) or [nginx/summit-web-cloudflare.conf](nginx/summit-web-cloudflare.conf).

### Production Checklist

- Set `SECRET_KEY` environment variable
- Use HTTPS (Nginx + Let's Encrypt or Cloudflare)
- Restrict database file permissions
- Never commit `.env` or secrets
- Set up rate limiting (Cloudflare or Nginx)

## Troubleshooting

### "Database file not found"
Ensure you're running from `web-app/` and databases exist in `../discord-bot/`. Run `python scripts/seed_databases.py` to create test databases.

### "SECRET_KEY must be set in production"
```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### Discord OAuth "Invalid Redirect URI"
Add `http://localhost:5000/auth/discord/callback` to your Discord app's OAuth2 redirect URIs in the [Developer Portal](https://discord.com/developers/applications).

### API Returns Empty Data
Check that databases have data. Run `python scripts/seed_databases.py` or use the Discord bot to populate real data.

## Additional Resources

- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - Full API reference
- [DEPLOYMENT.md](DEPLOYMENT.md) - Detailed deployment guide
- [../discord-bot/](../discord-bot/) - Discord bot
