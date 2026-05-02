# Summit Discord Bot

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-blue.svg)](https://github.com/Rapptz/discord.py)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Discord bot and web platform for the **Sorcery: Contested Realm** card game community.

## What's in This Repo

| System | Description |
|---|---|
| `discord-bot/` | Python Discord bot — matchmaking, ELO rankings, community features |
| `web-app/` | Flask REST API + React frontend — leaderboards, stats, deck browser, admin tools |

---

## Quick Start

### Discord Bot

```bash
cd discord-bot
pip install -r requirements.txt
cp config.example.py config.py   # Fill in your server/channel IDs
```

Create `discord-bot/.env`:
```env
TOKEN=your_discord_bot_token_here
```

```bash
python main.py
```

### Web App

**Flask API (backend):**
```bash
cd web-app
pip install -r requirements.txt
python scripts/seed_databases.py   # Create test databases
python app.py                      # Runs on port 5000
```

**React Frontend:**
```bash
cd web-app/frontend
npm install
npm run dev   # Vite dev server on port 5173, proxies to Flask
```

Open http://localhost:5173

---

## Project Structure

```
SummitDiscordBot/
├── discord-bot/
│   ├── cogs/               # Command modules (LFG, ELO, Fun, etc.)
│   │   └── lfg/            # LFG package (queue, matching, reporting)
│   ├── repositories/       # Data access layer
│   ├── services/           # Business logic
│   ├── utils/              # Shared utilities
│   ├── tests/              # Test suite (87+ tests)
│   ├── scripts/            # Helper scripts
│   ├── config.py           # Configuration (gitignored)
│   └── main.py             # Entry point
│
└── web-app/
    ├── app.py              # Flask app factory
    ├── webapp_config.py    # Configuration
    ├── gunicorn_config.py  # Production WSGI config
    ├── routes/
    │   ├── auth.py         # Discord & Google OAuth
    │   └── api/            # REST API endpoints
    ├── services/           # Business logic
    ├── repositories/       # SQLite data access
    ├── utils/              # Auth, formatting, versioning
    ├── migrations/         # Database migrations (auto-run on startup)
    ├── scripts/
    │   └── seed_databases.py  # Create test databases for local dev
    ├── frontend/           # React + Vite SPA
    │   └── src/
    │       ├── pages/      # One component per route
    │       ├── components/ # Shared UI components
    │       ├── api/        # Typed API fetch wrappers
    │       └── App.jsx     # Router
    ├── static/             # Served assets (favicon, element images)
    ├── templates/
    │   └── avatar_imgs/    # Avatar image files
    ├── top-8-decks-by-event/  # Tournament deck JSON files
    ├── nginx/              # Nginx configs
    └── systemd/            # systemd service file
```

---

## Tech Stack

### Discord Bot
- **discord.py** — Discord API
- **SQLite** — Match records, ELO, scores
- **OpenAI API** — GPT responses for fun cog
- **pytest** — Tests

### Web App
- **Flask** — REST API (Python)
- **React + Vite** — Frontend SPA
- **Tailwind CSS** — Styling
- **SQLite** — Shared databases with the bot
- **Gunicorn** — WSGI server
- **Nginx + Cloudflare** — Reverse proxy and CDN

---

## Bot Commands

**Prefix (`!`):** `!lfg`, `!leave`, `!challenge @user`, `!leaderboard`, `!stats`, `!match_history`, `!deck <url>`

**Slash (`/`):** Same commands available as slash commands — `/lfg`, `/challenge`, `/leaderboard`, `/stats`, etc.

---

## Tests

```bash
cd discord-bot
pytest tests/ -v                      # All tests
pytest tests/test_lfg_queue.py -v    # Specific file
pytest -k "test_queue" -v             # By name pattern
```

87+ tests covering queue logic, ELO calculations, match reporting, database operations, and end-to-end workflows.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for full setup instructions and PR guidelines.

Quick steps:
1. Fork and clone
2. Set up bot + web app (see CONTRIBUTING.md)
3. Create a branch: `git checkout -b feature/my-feature`
4. Make changes with tests
5. Open a PR

---

## Documentation

- [CLAUDE.md](CLAUDE.md) — Architecture reference (also used by Claude Code)
- [CONTRIBUTING.md](CONTRIBUTING.md) — Dev setup and PR process
- [web-app/DEPLOYMENT.md](web-app/DEPLOYMENT.md) — Production deployment
- [web-app/API_DOCUMENTATION.md](web-app/API_DOCUMENTATION.md) — API reference

---

## Security

- Secrets in `.env` and `config.py` (gitignored — never commit these)
- SQL injection prevention via parameterized queries
- Rate limiting via Cloudflare
- Input validation on all API endpoints

---

**Made for the Sorcery: Contested Realm community**
