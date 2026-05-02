# Contributing to Summit Discord Bot

Thank you for your interest in contributing! This guide covers how to set up a local dev environment, make changes, and submit a PR.

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm** (for the React frontend)
- **Git**

---

## Setting Up Your Dev Environment

### 1. Fork and Clone

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR_USERNAME/SummitDiscordBot.git
cd SummitDiscordBot
```

### 2. Set Up the Discord Bot

```bash
cd discord-bot
pip install -r requirements.txt
cp config.example.py config.py   # Then fill in your test server IDs
```

Create `discord-bot/.env`:
```env
TOKEN=your_test_bot_token_here
OPENAI_API_KEY=your_openai_key_here   # Optional — only needed for fun cog
```

To get a test bot token:
1. Go to https://discord.com/developers/applications → New Application
2. Go to **Bot** tab → copy the token
3. Enable intents: **Message Content**, **Server Members**, **Presence**
4. Invite to a test server: `https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=8&scope=bot%20applications.commands`
5. Enable Developer Mode in Discord → right-click channels → Copy ID → fill in `config.py`

### 3. Set Up the Web App — Flask Backend

```bash
cd web-app
pip install -r requirements.txt
```

Seed local test databases (creates sample data in `../discord-bot/`):
```bash
python scripts/seed_databases.py
```

Run the Flask API:
```bash
python app.py   # Runs on http://localhost:5000
```

For full OAuth login functionality, add to `discord-bot/.env`:
```env
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=http://localhost:5173/auth/discord/callback
SECRET_KEY=any_random_string_for_local_dev
```

### 4. Set Up the Web App — React Frontend

```bash
cd web-app/frontend
npm install
npm run dev   # Starts Vite dev server on http://localhost:5173
```

Vite automatically proxies `/api`, `/auth`, `/static`, `/avatar-images`, and `/card-images` to the Flask backend at port 5000. You need **both** running for the full site to work.

### 5. Run the Tests

```bash
# Discord bot tests
cd discord-bot
pytest tests/ -v

# Run a specific test file
pytest tests/test_lfg_queue.py -v
```

---

## Making Changes

### Creating a Branch

```bash
git checkout -b feature/my-feature-name
# or
git checkout -b fix/bug-description
```

### What Goes Where

| What you're changing | Where |
|---|---|
| Discord bot commands | `discord-bot/cogs/` |
| Bot business logic | `discord-bot/services/` |
| Bot database queries | `discord-bot/repositories/` |
| Flask API endpoints | `web-app/routes/api/` |
| Web app business logic | `web-app/services/` |
| Web app database queries | `web-app/repositories/` |
| React pages | `web-app/frontend/src/pages/` |
| React components | `web-app/frontend/src/components/` |
| API fetch wrappers | `web-app/frontend/src/api/` |

### Adding a New Web Page

1. Create `web-app/frontend/src/pages/MyPage.jsx`
2. Add a fetch function in `web-app/frontend/src/api/`
3. Register the route in `web-app/frontend/src/App.jsx`

### Adding a New API Endpoint

Add to the relevant file in `web-app/routes/api/`. All endpoints return JSON — no template rendering.

### Adding a New Bot Command

See the patterns in `CLAUDE.md` for prefix commands, slash commands, and new cogs.

---

## Before Submitting a PR

### Checklist

- [ ] Tests pass: `cd discord-bot && pytest tests/ -v`
- [ ] No Python syntax errors: `python -m py_compile <changed_files>`
- [ ] React builds without errors: `cd web-app/frontend && npm run build`
- [ ] Tested the feature manually (bot in test server, or web app locally)
- [ ] No secrets or API keys committed
- [ ] `config.py` and `.env` not committed
- [ ] CLAUDE.md updated if you changed architecture or added major features

### Code Standards

- Follow existing patterns in the codebase (see `CLAUDE.md`)
- No hardcoded Discord IDs or secrets — use `config.py` / environment variables
- Keep PRs focused. One feature or fix per PR.
- Under 500 lines changed when possible — if larger, explain why in the PR description

---

## Submitting a PR

```bash
git add <specific files>   # Avoid git add . to prevent committing secrets
git commit -m "feat: short description of what changed"
git push origin feature/my-feature-name
```

Then open a Pull Request on GitHub from your fork to `main`.

### PR Description

Include:
- **What** changed and **why**
- Steps to test it locally
- Screenshots if it's a UI change

### After Opening the PR

1. GitHub Actions runs automated tests — fix any failures
2. A maintainer will review and may request changes
3. Once approved, the maintainer merges
4. The deploy workflow auto-deploys to production

---

## Reporting Bugs

Open a GitHub Issue with:
1. What happened vs. what you expected
2. Steps to reproduce
3. Python version, OS, and relevant error logs

## Feature Requests

Open a GitHub Issue before starting work on large features to align on approach first.

## Getting Help

- Read `CLAUDE.md` for architecture details
- Open a GitHub Issue for questions
- Join the [Sorcerer's Summit Discord](https://discord.gg/sorcererssummit)
