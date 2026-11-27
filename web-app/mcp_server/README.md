# Summit MCP server

Read-only Summit data for AI apps (Claude, ChatGPT, Cursor, ...) at
`https://sorcererssummit.com/mcp`. No login. Players add that address as a
custom connector; the Help page has the steps (`/help#ai-apps`).

## How it works

```
AI app ──HTTPS──> Cloudflare ──> nginx /mcp ──> summit-mcp (127.0.0.1:8765)
                                                     │ cache + 1 request at a time
                                                     ▼
                                    gunicorn /tmp/summit-web.sock (/api/*)
```

- Its own systemd service (`systemd/summit-mcp.service`) and venv
  (`mcp_server/venv`), so restarting it never touches the site or the bot.
- Reads the site's own `/api` as a **logged-out visitor** (site token, never
  an API key: an API key counts as admin in `utils/auth.is_admin`). Privacy
  settings and hidden sections behave exactly as on the site.
- Every answer is cached in memory (10 min, 30-60 min for slow pages); at most
  one request goes to the site at a time; 60 MCP requests per visitor IP per
  minute.
- Never calls Play Sorcery Online. Card numbers use the saved release
  snapshots; `top_staples` never sends a custom date range (that one would
  ask PSO live). A test checks the code holds no PSO address.

## Rules (tested in `tests/test_mcp_server.py`)

- No ranked deck lists or links. Every tool's answer goes through
  `safety.strip_deck_data`; only the Top 8 tools link decks, and only Top 8
  decks on our own `/deck-rec/<id>` page.
- No leaderboard tool and no ranks or ratings for players (Bruce, 2026-11-27).
- Read-only: no tool changes anything.

## Tools

| Tool | Uses |
| --- | --- |
| player_lookup | /api/players/search, /api/player/&lt;id&gt; (record, Avatars, last 10 games; no rank/rating) |
| avatar_stats | /api/avatars, /api/avatar/&lt;name&gt;, /api/avatar/&lt;name&gt;/matchups |
| card_stats | /api/card/&lt;name&gt; |
| top_staples | /api/staples (release windows only) |
| meta_report | /api/meta-reports, /api/meta-reports/&lt;slug&gt; |
| meta_trends | /api/deck-archetypes/trends |
| top8_events, top8_event_decks, top8_card_search | /api/top-8-events, /api/events/&lt;folder&gt;, /api/top-8-events/card-search |
| matchup_prep | avatar matchups + tournament archetype card patterns + recent Top 8 lists |
| deck_check | /api/deck-builder/fetch (Curiosa link) or a pasted list, tournament archetypes, Meta Report deck types, /api/card |
| store_products | /api/store/products (public listings only) |
| ranked_recap | /api/match-history/recap |

Prompts: Prep me for a matchup, Explain this release's meta report, Review
my deck, Help me pick an avatar, What changed in ranked this week?

## Run locally

```bash
cd web-app
python -m venv mcp_server/venv && mcp_server/venv/bin/pip install -r mcp_server/requirements.txt pytest
python app.py &                                   # Flask dev server on :5000
SUMMIT_MCP_SITE_URL=http://localhost:5000 mcp_server/venv/bin/python -m mcp_server.server
mcp_server/venv/bin/python -m pytest mcp_server/tests -q
```

Settings (env): `SUMMIT_MCP_SITE_SOCKET`, `SUMMIT_MCP_SITE_URL`,
`SUMMIT_MCP_HOST`, `SUMMIT_MCP_PORT`, `SUMMIT_MCP_CACHE_TTL`,
`SUMMIT_MCP_RATE_LIMIT`, `SUMMIT_MCP_UPSTREAM_CONCURRENCY`.

Health check: `curl http://127.0.0.1:8765/mcp-health`.
