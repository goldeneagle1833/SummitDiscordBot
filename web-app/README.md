# Summit Web App

A Flask web application providing leaderboards, statistics, match history, deck viewing, and REST API for the Summit Sorcery: Contested Realm community.

## Features

- **Leaderboards**: View ELO rankings with filtering by format and event tier
- **Player Stats**: Detailed player profiles with match history and deck usage
- **Deck Browser**: Browse top-performing decks from major tournaments
- **Match Reports**: Web-based match reporting with deck validation
- **REST API**: Comprehensive API for players, matches, cards, and statistics
- **Discord OAuth**: Secure authentication via Discord
- **Rules Assistant**: Integration with SorceryAI RAG system

## Prerequisites

- **Python 3.8+** (Python 3.12+ recommended)
- **pip** (Python package installer)
- **Git** (for cloning the repository)
- **Discord Bot** databases (the web app reads from shared SQLite databases)

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/SummitDiscordBot.git
cd SummitDiscordBot/web-app
```

### 2. Create Virtual Environment (Recommended)

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

### 4. Set Up Environment Variables (Optional for Basic Usage)

The web app shares the `.env` file with the Discord bot. For basic local testing, you can run without any `.env` file - the app will use development defaults.

**For full functionality**, create `discord-bot/.env` with:

```env
# Optional: Discord OAuth (required for login features)
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
DISCORD_REDIRECT_URI=http://localhost:5000/auth/discord/callback

# Optional: Secret key for sessions (auto-generated in dev mode if not set)
SECRET_KEY=your_secret_key_here

# Optional: OpenAI API Key (for SorceryAI integration)
OPENAI_API_KEY=your_openai_api_key

# Optional: External API keys (comma-separated)
API_KEYS=key1,key2,key3
```

**Generate a secret key** (for production):
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Get Discord OAuth credentials**:
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create or select your application
3. Go to OAuth2 settings
4. Copy Client ID and Client Secret
5. Add redirect URI: `http://localhost:5000/auth/discord/callback`

### 5. Set Up Databases

The web app reads from SQLite databases created by the Discord bot. You have two options:

**Option A: Use Existing Bot Databases (Recommended)**

If you're running the Discord bot, the databases already exist in `discord-bot/`:
- `elo.db` - Player ELO ratings
- `match_records.db` - Match history with deck data
- `fart_scores.db` - Fart game scores
- `community.db` - Community data

The web app will automatically read from these files.

**Option B: Create Empty Test Databases**

For testing without the bot, create empty databases:

```bash
cd ../discord-bot
python scripts/create_test_databases.py
cd ../web-app
```

This creates minimal schema databases you can populate manually or via the API.

### 6. Run the Application

**Development Mode** (auto-reloads on code changes):
```bash
python app.py
```

The app will be available at: `http://localhost:5000`

**Production Mode** (with Gunicorn):
```bash
gunicorn -c gunicorn_config.py app:app
```

Production mode requires `SECRET_KEY` to be set in environment variables.

### 7. Verify Installation

Open your browser and navigate to:
- **Home**: http://localhost:5000
- **Leaderboard**: http://localhost:5000/leaderboard
- **API Status**: http://localhost:5000/api/status

## Project Structure

```
web-app/
├── app.py                      # Application factory and entry point
├── webapp_config.py            # Configuration (paths, OAuth, admins)
├── gunicorn_config.py          # Production WSGI server config
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── routes/                     # Route handlers (API layer)
│   ├── __init__.py
│   ├── pages.py               # HTML page routes
│   ├── auth.py                # Discord/Google OAuth routes
│   └── api/                   # REST API endpoints
│       ├── avatars.py
│       ├── cards.py
│       ├── games.py
│       ├── leaderboard.py
│       ├── matches.py
│       ├── players.py
│       ├── rules.py
│       ├── streamers.py
│       └── misc.py
│
├── services/                   # Business logic layer
│   ├── curiosa.py             # Curiosa API integration
│   ├── leaderboard.py         # Leaderboard calculations
│   ├── match.py               # Match processing
│   ├── player.py              # Player data aggregation
│   └── youtube.py             # YouTube API integration
│
├── repositories/               # Data access layer
│   ├── elo.py                 # ELO database operations
│   ├── events.py              # Event/tournament data
│   ├── fart.py                # Fart game data
│   └── matches.py             # Match history queries
│
├── utils/                      # Shared utilities
│   ├── auth.py                # Authentication helpers
│   ├── decorators.py          # Route decorators (API key, admin)
│   └── version.py             # App version constant
│
├── templates/                  # Jinja2 HTML templates
│   ├── index.html
│   ├── leaderboard.html
│   ├── player_profile.html
│   ├── match_report.html
│   ├── deck_view.html
│   └── ...
│
├── static/                     # Static assets
│   ├── css/
│   ├── js/
│   └── images/
│
├── top-8-decks-by-event/      # Tournament deck JSON files
├── card_images/               # Card image cache
├── migrations/                # Database migration scripts
└── systemd/                   # Production deployment configs
```

## API Documentation

The web app provides a comprehensive REST API. See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for details.

**Key Endpoints:**
- `GET /api/leaderboard` - ELO rankings with filtering
- `GET /api/players/{discord_id}` - Player profile and stats
- `GET /api/matches` - Match history with deck data
- `GET /api/cards` - Card database with stats
- `GET /api/avatars` - Avatar statistics and meta analysis
- `POST /api/report-match` - Submit match results (requires API key)

## Configuration

### Environment Variables

All environment variables are **optional** for local development:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_CLIENT_ID` | No | None | Discord OAuth client ID |
| `DISCORD_CLIENT_SECRET` | No | None | Discord OAuth secret |
| `DISCORD_REDIRECT_URI` | No | `http://localhost:5000/auth/discord/callback` | OAuth callback URL |
| `SECRET_KEY` | Production only | Auto-generated | Flask session secret key |
| `OPENAI_API_KEY` | No | None | OpenAI API key for rules assistant |
| `API_KEYS` | No | Empty | Comma-separated API keys for external integrations |
| `ELO_DB_PATH` | No | `../discord-bot/elo.db` | Custom ELO database path |
| `MATCH_RECORDS_DB_PATH` | No | `../discord-bot/match_records.db` | Custom match database path |
| `FART_SCORES_DB_PATH` | No | `../discord-bot/fart_scores.db` | Custom fart database path |

### Database Configuration

By default, the web app reads databases from `../discord-bot/`. To use custom database locations, set environment variables:

```env
ELO_DB_PATH=/path/to/elo.db
MATCH_RECORDS_DB_PATH=/path/to/match_records.db
FART_SCORES_DB_PATH=/path/to/fart_scores.db
COMMUNITY_DB_PATH=/path/to/community.db
```

### Admin Configuration

Admin Discord IDs are configured in `webapp_config.py`. Admins have full access to all features including match editing and deletion.

## Development

### Auto-Reload

The app runs in debug mode by default, which means:
- **Templates auto-reload** - Changes to HTML/CSS reflect immediately
- **Python auto-reload** - Changes to Python files restart the server
- **Detailed error pages** - Stack traces displayed in browser

### Running Tests

```bash
cd ../discord-bot
pytest tests/ -v
```

The test suite covers shared utilities and database operations used by both the bot and web app.

## Production Deployment

### Using Gunicorn

```bash
gunicorn -c gunicorn_config.py app:app
```

Configuration in `gunicorn_config.py`:
- **Workers**: 4 (adjust based on CPU cores)
- **Bind**: `0.0.0.0:8000`
- **Timeout**: 120 seconds
- **Access logs**: Enabled

### Using systemd (Linux)

See [systemd/summit-web.service](systemd/summit-web.service) for the service configuration.

```bash
sudo cp systemd/summit-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable summit-web
sudo systemctl start summit-web
```

### Nginx Configuration

See [nginx/summit-web.conf](nginx/summit-web.conf) for reverse proxy setup.

### Security Checklist

- [ ] Set `SECRET_KEY` environment variable
- [ ] Use HTTPS in production (Nginx + Cloudflare recommended)
- [ ] Restrict database file permissions (`chmod 600 *.db`)
- [ ] Never commit `.env` or `webapp_config.py` with secrets
- [ ] Set up rate limiting (Cloudflare or Nginx)
- [ ] Enable CORS only for trusted origins
- [ ] Validate all API inputs

## Troubleshooting

### "Database file not found"

**Problem**: Web app can't find Discord bot databases.

**Solution**:
1. Ensure you're running from `web-app/` directory
2. Check that databases exist in `../discord-bot/`
3. Or create test databases: `python discord-bot/scripts/create_test_databases.py`

### "SECRET_KEY must be set in production"

**Problem**: Running in production mode without `SECRET_KEY` environment variable.

**Solution**:
```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

Or add to `discord-bot/.env`:
```env
SECRET_KEY=your_generated_key_here
```

### Discord OAuth "Invalid Redirect URI"

**Problem**: OAuth callback fails with redirect URI error.

**Solution**:
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application → OAuth2 → Redirects
3. Add: `http://localhost:5000/auth/discord/callback` (development) or your production URL

### Templates Not Updating

**Problem**: HTML changes don't reflect in browser.

**Solution**:
1. Hard refresh browser: `Ctrl+F5` (Windows) or `Cmd+Shift+R` (Mac)
2. Check `app.config['TEMPLATES_AUTO_RELOAD'] = True` is set (enabled by default)
3. Restart the Flask app

### API Returns Empty Data

**Problem**: API endpoints return empty arrays or `null`.

**Solution**: Ensure databases have data:
- Run the Discord bot to populate databases with match data
- Or manually insert test data via SQL
- Check database paths in `webapp_config.py`

## Additional Resources

- **API Documentation**: [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- **Tailwind CSS Guide**: [TAILWIND.md](TAILWIND.md)
- **Discord Bot Setup**: [../discord-bot/README.md](../discord-bot/README.md)
- **SorceryAI Setup**: [../SorceryAI/README.md](../SorceryAI/README.md)

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and test locally
4. Run tests: `pytest tests/ -v`
5. Commit changes: `git commit -m "Add your feature"`
6. Push to branch: `git push origin feature/your-feature`
7. Open a Pull Request

## License

See [LICENSE](../LICENSE) for details.

## Support

For issues, questions, or contributions:
- **GitHub Issues**: https://github.com/yourusername/SummitDiscordBot/issues
- **Discord**: Join the Summit community server

---

**Version**: 2.0.0
**Last Updated**: 2026-03-12
