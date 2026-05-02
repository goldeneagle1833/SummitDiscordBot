# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Summit Discord Bot is a community bot for "Sorcery: Contested Realm" card game. It consists of two integrated systems:

- **discord-bot/** - Python Discord bot (discord.py 2.3+) for matchmaking, ELO ranking, and community features
- **web-app/** - Flask REST API + React frontend for leaderboards, stats, deck viewing, and community tools

## Common Commands

### Discord Bot
```bash
pip install -r discord-bot/requirements.txt
python discord-bot/main.py

# Run tests
cd discord-bot && pytest tests/ -v
```

### Web App — Flask API
```bash
pip install -r web-app/requirements.txt
cd web-app && python app.py        # Development (port 5000)
gunicorn -c gunicorn_config.py     # Production
```

### Web App — React Frontend
```bash
cd web-app/frontend
npm install
npm run dev     # Dev server (Vite, port 5173) — proxies /api, /auth, /static to Flask
npm run build   # Build to web-app/frontend/dist/ for production
```

### Seed Test Databases
```bash
cd web-app && python scripts/seed_databases.py
```

## Architecture

### Discord Bot Cog System

Commands are organized into Cogs (modular command handlers) in `discord-bot/cogs/`:
- `lfg/` - Looking For Game queue and matchmaking (package, split from one large file)
- `elo.py` - ELO ranking, leaderboards, stats
- `fun.py` - Fart game with OpenAI responses
- `shop.py` - In-game shop and purchases
- `utility.py` - Help, deck checking
- `anti_spam.py` - Spam protection system
- `streaming.py` - Streaming detection and announcements
- `purchase_tracking.py` - Discord monetization/purchase tracking
- `slash_commands.py` - Delegates slash commands to existing cog functions (DRY pattern)

Utilities in `discord-bot/utils/`:
- `database.py` - Facade re-exporting from repositories/services
- `deck_checker.py` - Curiosa API integration for deck/card data
- `constants.py` - Shared constants and configuration values

### Slash Command Delegation Pattern

Slash commands don't duplicate logic. They:
1. Defer the interaction (prevent timeout)
2. Get the target cog via `bot.get_cog("CogName")`
3. Create context from interaction
4. Call the existing prefix command function

### Web Application Architecture

The web app is split into a **Flask REST API** (backend) and a **React SPA** (frontend).

In production (Cloudflare Nginx config), Nginx serves:
- `/api/*`, `/auth/*`, `/static/*` → Flask (Gunicorn)
- Everything else → React SPA from `frontend/dist/index.html`

**Flask API** (`web-app/`):
- `routes/auth.py` - Discord & Google OAuth flows
- `routes/api/` - REST API endpoints (no HTML rendering)

**Services** (`web-app/services/`):
- `curiosa.py` - Curiosa API integration
- `leaderboard.py` - Leaderboard business logic (7 types)
- `match.py` - Match processing
- `match_confirmation.py` - 48-hour confirmation workflow
- `player.py` - Player data aggregation
- `seasons.py` - Season management
- `admin.py`, `paper_elo.py`, `external_match.py`, `limited_service.py`, `deck_similarity.py`, `youtube.py`, `pilots.py`

**Repositories** (`web-app/repositories/`):
- `elo.py` - ELO standings (elo.db)
- `matches.py` - Match history (match_records.db)
- `events.py` - Tournament deck data (JSON files)
- `fart.py`, `community.py`, `curios.py`, `audit.py`, `analytics.py`
- `user_profiles.py`, `match_confirmation.py`, `seasons.py`, `limited_repo.py`
- `deck_rec_repo.py`, `avatar_image_settings.py`

**React Frontend** (`web-app/frontend/src/`):
- `pages/` - One component per route (Leaderboard, Player, Events, Cards, etc.)
- `components/` - Shared UI components (layout, player, deck, admin)
- `api/` - Typed fetch wrappers for all Flask API endpoints
- `context/AuthContext.jsx` - Auth state
- `App.jsx` - Router with all routes defined

## Key Configuration

- `discord-bot/config.py` - Centralized bot config (gitignored): API keys, channel/guild/role IDs
- `web-app/webapp_config.py` - Web app configuration (DB paths, OAuth, admins)
- `web-app/gunicorn_config.py` - Production WSGI server config
- `discord-bot/.env` - Bot token and API keys (gitignored)

## Database

SQLite databases in `discord-bot/` (gitignored):
- `match_records.db` - Match history, confirmations, profiles, seasons, audit log
- `elo.db` - Player ratings, events, paper/limited standings
- `fart_scores.db` - Fart game scores
- `community.db` - Community links, curio tracking

The Discord bot accesses databases via `discord-bot/utils/database.py`. The web app uses the repository pattern via `web-app/repositories/`.

Database migrations run automatically on Flask startup via `web-app/migrations/`.

## CI/CD and Deployment

**GitHub Actions** (`.github/workflows/`):
- `deploy-bot.yml` - Discord bot deployment
- `deploy-web.yml` - Web app deployment (runs `npm run build`, deploys Flask + React dist)

**Production**: systemd + Gunicorn + Nginx + Cloudflare.
- React SPA served directly by Nginx from `frontend/dist/`
- Flask handles only `/api/`, `/auth/`, `/static/` routes
- Config: `web-app/nginx/summit-web-cloudflare.conf`
- See `web-app/DEPLOYMENT.md`

## External Integrations

- **Discord API** - via discord.py (prefix `!` and slash `/` commands)
- **OpenAI API** - GPT models for fun cog responses
- **Curiosa API** - Deck/card data via `utils/deck_checker.py` and `web-app/services/curiosa.py`
- **YouTube API** - Streaming integration via `web-app/services/youtube.py`
- **Discord OAuth** - Web app authentication via `web-app/routes/auth.py`
- **Google OAuth** - Alternative login via `web-app/routes/auth.py`

## Adding New Discord Commands

### Prefix Command (in existing cog)
```python
@commands.command()
async def my_command(self, ctx, param: str):
    await ctx.send(f"Response: {param}")
```

### Slash Command (add to slash_commands.py)
```python
@app_commands.command(name="my_command", description="Description")
async def my_command_slash(self, interaction: discord.Interaction, param: str):
    await interaction.response.defer()
    cog = self.bot.get_cog("TargetCog")
    ctx = await self.bot.get_context(interaction)
    await cog.my_command(ctx, param)
```

### New Cog
1. Create file in `discord-bot/cogs/`
2. Define class inheriting from `commands.Cog`
3. Add `setup()` function at bottom
4. Import and load in `main.py`

## Adding New Web App Pages

### New API Endpoint (Flask)
Add to the appropriate file in `web-app/routes/api/`. All endpoints return JSON.

### New Frontend Page (React)
1. Create `web-app/frontend/src/pages/MyPage.jsx`
2. Add API call in `web-app/frontend/src/api/`
3. Register route in `web-app/frontend/src/App.jsx`

## Important Notes

- LFG queue is stored in memory (resets on bot restart)
- Both prefix (`!`) and slash (`/`) commands are supported
- `config.py` and `.env` are gitignored — never commit secrets
- Tournament deck data stored in `web-app/top-8-decks-by-event/` (JSON files per event)
- Bot requires intents: `message_content`, `members`, `presences` (for streaming detection)
- Bot logging goes to `bot.log` (gitignored)
- The bot runs in the cloud — can't test locally by running it; verify with syntax checks and import tests
