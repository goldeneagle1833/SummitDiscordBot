# Summit Discord Bot 🎴

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-blue.svg)](https://github.com/Rapptz/discord.py)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A comprehensive Discord bot for the **Sorcery: Contested Realm** card game community, featuring matchmaking, ELO rankings, and tournament tracking.

## 🌟 Features

### Discord Bot

- **🎮 LFG (Looking For Game) System** - Queue-based matchmaking with challenge support
- **📊 ELO Ranking System** - Competitive player rankings with win/loss tracking
- **🏆 Tournament Management** - Event tracking and leaderboards
- **🎲 Fun Mini-Games** - Community engagement features
- **🛡️ Anti-Spam Protection** - Rate limiting and spam detection
- **📡 Streaming Integration** - Auto-announcements for streamers

### Web Application

- **📈 Live Leaderboards** - Real-time ELO rankings and statistics
- **🃏 Deck Viewer** - Browse tournament-winning decklists
- **📊 Match History** - Detailed game records with deck data
- **🔍 Card Database** - Searchable card database via Curiosa API
- **🎥 YouTube Integration** - Featured content and streaming

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Discord Bot Token ([Create one here](https://discord.com/developers/applications))

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/YOUR_USERNAME/SummitDiscordBot.git
   cd SummitDiscordBot
   ```

2. **Set up Discord Bot**

   ```bash
   cd discord-bot
   pip install -r requirements.txt
   cp config.example.py config.py
   ```

3. **Configure environment**

   Create `discord-bot/.env`:

   ```env
   TOKEN=your_discord_bot_token_here
   ```

   Edit `discord-bot/config.py` with your Discord server IDs.

4. **Create test databases**

   ```bash
   python scripts/create_test_databases.py
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

### Running Tests

```bash
cd discord-bot
pytest tests/ -v
```

## 📂 Project Structure

```
SummitDiscordBot/
├── discord-bot/              # Main Discord bot application
│   ├── cogs/                # Command modules (LFG, ELO, Fun, etc.)
│   │   └── lfg/            # LFG package (queue, matching, reporting)
│   ├── repositories/        # Data access layer
│   ├── services/           # Business logic
│   ├── utils/              # Utilities (database, text, deck checking)
│   ├── tests/              # Test suite (87+ tests)
│   ├── scripts/            # Helper scripts
│   ├── config.py           # Configuration (gitignored)
│   └── main.py             # Entry point
│
├── web-app/                 # Flask web application
│   ├── routes/             # API and page routes
│   ├── services/           # Business logic services
│   ├── repositories/       # Data repositories
│   ├── templates/          # Jinja2 HTML templates
│   ├── static/             # CSS, JS, images
│   └── app.py              # Flask app entry point
│
├── docs/                    # Documentation
├── CLAUDE.md               # Project architecture guide
├── CONTRIBUTING.md         # Contribution guidelines
├── TESTING.md              # Testing documentation
└── GITHUB_SETUP_GUIDE.md   # Repository setup guide
```

## 🎮 Bot Commands

### Prefix Commands (!)

- `!lfg` - Join the looking-for-game queue
- `!leave` - Leave the queue
- `!challenge @user` - Challenge a specific player
- `!leaderboard` - View ELO rankings
- `!stats [@user]` - View player statistics
- `!match_history [@user]` - View recent matches
- `!deck <url>` - Check deck validity

### Slash Commands (/)

- `/lfg` - Join queue (slash command version)
- `/challenge` - Challenge a player
- `/leaderboard` - View rankings
- `/stats` - View statistics
- And more...

## 🛠️ Tech Stack

### Discord Bot

- **discord.py** - Discord API wrapper
- **SQLite** - Database (match records, ELO, scores)
- **OpenAI API** - GPT for fun cog responses
- **pytest** - Testing framework

### Web Application

- **Flask** - Web framework
- **Jinja2** - Template engine
- **Gunicorn** - WSGI server
- **Nginx** - Reverse proxy
- **YouTube API** - Video integration

### Infrastructure

- **GitHub Actions** - CI/CD
- **systemd** - Service management
- **Cloudflare** - CDN and DDoS protection

## 🧪 Testing

The project includes a comprehensive test suite with 87+ passing tests:

```bash
cd discord-bot
pytest tests/ -v                       # Run all tests
pytest tests/test_lfg_queue.py -v     # Run specific test file
pytest -k "test_queue" -v              # Run tests matching pattern
```

**Test Coverage:**

- ✅ Queue operations and matching logic
- ✅ ELO calculations and rankings
- ✅ Match reporting and confirmation
- ✅ Database operations
- ✅ URL scrubbing and validation
- ✅ End-to-end workflows

See [TESTING.md](TESTING.md) for detailed testing documentation.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Quick Contribution Steps:

1. Fork the repository
2. Create a test environment (see [CONTRIBUTING.md](CONTRIBUTING.md))
3. Make your changes with tests
4. Submit a pull request

**Before submitting:**

- ✅ Tests pass: `pytest tests/ -v`
- ✅ No syntax errors: `python -m py_compile cogs/**/*.py`
- ✅ Code follows existing patterns
- ✅ Documentation updated

## 📚 Documentation

- **[CLAUDE.md](CLAUDE.md)** - Comprehensive architecture documentation
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines
- **[TESTING.md](TESTING.md)** - Testing strategies and setup
- **[GITHUB_SETUP_GUIDE.md](GITHUB_SETUP_GUIDE.md)** - Repository configuration
- **[web-app/DEPLOYMENT.md](web-app/DEPLOYMENT.md)** - Web app deployment

## 🔧 Configuration

### Discord Bot Setup

1. Create bot application at https://discord.com/developers/applications
2. Enable these intents:
   - ✅ Message Content Intent
   - ✅ Server Members Intent
   - ✅ Presence Intent
3. Invite bot with permissions: `Administrator` or specific permissions
4. Configure `config.py` with your server/channel IDs

### Database Configuration

- **SQLite databases** (auto-created on first run)
- Test databases: `discord-bot/test_data/`
- Production databases: `discord-bot/*.db` (gitignored)

### API Keys

Required API keys (add to `.env`):

- `TOKEN` - Discord bot token

## 🌐 Web Application

The web application provides a public interface for leaderboards and statistics.

### Running Locally

```bash
cd web-app
pip install -r requirements.txt
python app.py
```

Visit: http://localhost:5000

### Production Deployment

```bash
gunicorn -c gunicorn_config.py
```

See [web-app/DEPLOYMENT.md](web-app/DEPLOYMENT.md) for full deployment guide.

## 📊 Statistics

- **87+ tests** with 100% pass rate
- **10,000+ lines** of Python code
- **2 integrated systems** (bot, web)
- **1,000+ users** served (production stats)

## 🔐 Security

- ✅ Secrets stored in `.env` (gitignored)
- ✅ Rate limiting and anti-spam
- ✅ Input validation and sanitization
- ✅ SQL injection prevention (parameterized queries)
- ✅ XSS protection in web app

**Never commit:**

- `config.py` (contains secrets)
- `.env` (contains API keys)
- `*.db` (contains user data)

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Sorcery: Contested Realm** community
- **discord.py** library and contributors
- **OpenAI** for GPT and embedding models
- **Curiosa.io** for deck/card data API

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/YOUR_USERNAME/SummitDiscordBot/issues)
- **Discord**: [Sorcerer's Summit](https://discord.gg/sorcererssummit)
- **Documentation**: See [docs/](docs/) folder

## 🗺️ Roadmap

- [ ] Advanced statistics and analytics
- [ ] Localizing language
- [ ] Player achivements

## 🏗️ Development

### Setting Up Development Environment

```bash
# Clone and set up
git clone https://github.com/YOUR_USERNAME/SummitDiscordBot.git
cd SummitDiscordBot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install all dependencies
pip install -r discord-bot/requirements.txt
pip install -r web-app/requirements.txt

# Set up test databases
python discord-bot/scripts/create_test_databases.py

# Run tests
pytest discord-bot/tests/ -v
```

### Code Style

- Follow PEP 8 Python style guide
- Use type hints where appropriate
- Document functions with docstrings
- Keep functions focused and small
- Write tests for new features

## 💻 Architecture

### Bot Architecture

- **Cogs**: Modular command handlers (`cogs/`)
- **Repositories**: Data access layer (`repositories/`)
- **Services**: Business logic (`services/`)
- **Utils**: Shared utilities (`utils/`)

### Key Patterns

- **Facade Pattern**: `utils/database.py` provides unified interface
- **Repository Pattern**: Separation of data access and business logic
- **Package Structure**: Large cogs split into packages (e.g., `cogs/lfg/`)
- **Config Centralization**: All IDs in `config.py`, never hardcoded

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.

---

**Made with ❤️ for the Sorcery: Contested Realm community**

_Star this repo if you find it useful!_ ⭐
