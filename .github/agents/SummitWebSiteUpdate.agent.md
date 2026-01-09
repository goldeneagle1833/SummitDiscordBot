---
description: "Agent for implementing the Summit Web App rework following WEB_APP_REWORK_PLAN.md. Use this agent to create components, pages, styles, and routes for the web application redesign."
tools: ["vscode", "execute", "read", "edit", "search", "web", "agent", "todo"]
---

# Summit Web App Update Agent

This agent implements the web application rework as defined in `discord-bot/docs/development/WEB_APP_REWORK_PLAN.md`.

## Purpose

Systematically update the Flask web application with:

- New folder structure organized by component
- Reusable navbar with hamburger menu
- Global CSS with CSS custom properties
- Component-specific CSS files
- New page templates (Top 8 Decks, ELO pages, Deck Help)
- Updated routing in app.py

## Reference Documentation

Always read and follow: `discord-bot/docs/development/WEB_APP_REWORK_PLAN.md`

## Task Phases

### Phase 1: Create Folder Structure

Create the new directory structure in `web-app/`:

```
web-app/
├── static/
│   ├── css/
│   │   ├── global.css
│   │   ├── utilities.css
│   │   └── components/
│   │       ├── navbar.css
│   │       ├── leaderboard.css
│   │       ├── player-card.css
│   │       ├── avatar-grid.css
│   │       ├── event-card.css
│   │       ├── deck-viewer.css
│   │       ├── buttons.css
│   │       ├── forms.css
│   │       └── modals.css
│   └── js/
│       ├── main.js
│       └── components/
│           ├── navbar.js
│           ├── leaderboard.js
│           ├── deck-viewer.js
│           └── event-card.js
└── templates/
    ├── base.html
    ├── components/
    │   ├── navbar.html
    │   ├── footer.html
    │   ├── leaderboard_table.html
    │   ├── player_card.html
    │   ├── event_card.html
    │   ├── deck_viewer.html
    │   └── pagination.html
    ├── pages/
    │   ├── index.html
    │   ├── about.html
    │   ├── player.html
    │   ├── avatars.html
    │   ├── elo.html
    │   ├── elo_server.html
    │   ├── deck_help.html
    │   ├── top_8.html
    │   ├── stats.html
    │   └── help.html
    └── errors/
        ├── 404.html
        └── 500.html
```

### Phase 2: Create Global CSS

Create `static/css/global.css` with CSS custom properties:

```css
:root {
  --color-primary: #ffd700;
  --color-secondary: #1a1a2e;
  --color-background: #0f0f1a;
  --color-surface: #16213e;
  --color-text: #ffffff;
  --color-text-muted: #a0a0a0;
  --color-success: #4caf50;
  --color-error: #f44336;
  --font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.2);
  --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.3);
  --transition-fast: 0.15s ease;
  --transition-normal: 0.3s ease;
}
```

### Phase 3: Create Navbar Component

Create `templates/components/navbar.html` with:

- Top navbar with brand, Home, Discord, Patreon, About links
- Hamburger menu button on far left
- Sidebar that slides out with menu items:
  - Avatar Winrates (/avatars)
  - ELO Leaderboards (/elo) with sub-items
  - Deck Help (/deck-help)
  - Top 8 Decks (/top-8)
  - Statistics (/stats)
  - Help (/help)

Create `static/css/components/navbar.css` for styling.
Create `static/js/components/navbar.js` for hamburger toggle.

### Phase 4: Create Base Template

Create `templates/base.html` that:

- Includes global CSS files
- Includes navbar component
- Has blocks for: title, styles, content, scripts
- Includes footer component

### Phase 5: Create Page Templates

#### Top 8 Events List (`/top-8`)

- Lists all events from `top-8-decks-by-event/` folders
- Table with: Event Name, Date, Players
- Links to individual event pages

#### Event Detail (`/top-8/<folder>`)

- Shows Top 8 table: Place, Player, Avatar, Deck Link
- Deck links go to: https://curiosa.io/decks/{id}
- All Participants table below (if available)

#### ELO Pages

- `/elo` - Server selection page with cards
- `/elo/global` - Global leaderboard
- `/elo/server/<id>` - Server-specific leaderboard

#### Other Pages

- `/deck-help` - Deck building resources
- `/stats` - Statistics page (placeholder)
- `/help` - Help page (placeholder)

### Phase 6: Update Routes in app.py

Add Flask routes:

```python
@app.route('/top-8')
def top_8_events():
    # Load events from top-8-decks-by-event folders
    pass

@app.route('/top-8/<folder>')
def event_details(folder):
    # Load deck data, build Curiosa URLs
    pass

@app.route('/elo')
def elo_servers():
    pass

@app.route('/elo/global')
def elo_global():
    pass

@app.route('/elo/server/<int:guild_id>')
def elo_server(guild_id):
    pass

@app.route('/deck-help')
def deck_help():
    pass
```

### Phase 7: Migrate Existing Pages

Update existing templates to use new base.html:

- index.html -> pages/index.html (Global Leaderboard)
- about.html -> pages/about.html
- avatars.html -> pages/avatars.html
- player.html -> pages/player.html

## Key Implementation Details

### Curiosa Deck URLs

Build URLs from deck ID: `https://curiosa.io/decks/{deck_id}`

### Event JSON Structure

Each event folder may contain:

- `*Top8.json` - Top 8 decks
- `*.json` - All participants
- `event.json` - Event metadata (optional)

### Deck Normalization

Handle two JSON formats:

1. Curiosa format: `{ "id": "...", "username": "...", "avatar": [...] }`
2. Legacy format: `{ "Player Name, 1st, 6-0": { "Avatar": [...] } }`

## Execution Order

1. Read WEB_APP_REWORK_PLAN.md for full context
2. Create folder structure
3. Create global.css with CSS variables
4. Create utilities.css
5. Create navbar component (HTML, CSS, JS)
6. Create base.html template
7. Create component CSS files
8. Create page templates
9. Update app.py with new routes
10. Migrate existing templates
11. Test all routes

## Constraints

- Use Jinja2 template inheritance
- Use CSS custom properties from global.css
- No external CSS frameworks (custom CSS only)
- Maintain backwards compatibility with existing data
- Flask web framework with Python
