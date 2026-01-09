# Web App Rework Plan

This document outlines the redesign of the Summit web application with a new navigation structure and page layout.

---

## Overview

The web app will be restructured with:

1. **Global Leaderboard** as the main landing page
2. **Reusable Navbar Component** with branding and navigation
3. **Hamburger Menu** for additional page navigation
4. **Server-Specific ELO Pages** for multi-server support

---

## Navigation Structure

### Top Navbar Component

The navbar will be its own reusable component (`navbar.html` or `components/navbar.html`).

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ≡ │ Sorcerers Summit │ Home │ Discord │ Patreon │ About               │
└─────────────────────────────────────────────────────────────────────────┘
 ↑                        ↑
 Hamburger Menu           Main Navigation Links
```

**Main Navigation Links:**
| Link | Destination | Notes |
|------|-------------|-------|
| Sorcerers Summit | `/` | Logo/brand link to home |
| Home | `/` | Main leaderboard page |
| Discord | External | Link to Discord server invite |
| Patreon | External | Link to Patreon page |
| About | `/about` | About page |

### Hamburger Menu (☰)

Slides out from the left side with links to additional pages:

```
┌──────────────────────┐
│ MENU                 │
├──────────────────────┤
│ Avatar Winrates      │
│ ELO Leaderboards     │
│   └─ Global          │
│   └─ By Server       │
│ Deck Help            │
│ Top 8 Decks          │
│ Statistics           │
│ Help                 │
└──────────────────────┘
```

**Hamburger Menu Pages:**
| Page | Route | Status | Description |
|------|-------|--------|-------------|
| Avatar Winrates | `/avatars` | Placeholder | Win rates by avatar/character |
| ELO Leaderboards | `/elo` | Placeholder | Server-specific ELO pages |
| Global ELO | `/elo/global` | Placeholder | Combined global rankings |
| Server ELO | `/elo/server/<id>` | Placeholder | Per-server leaderboards |
| Deck Help | `/deck-help` | Placeholder | Deck building resources and guides |
| Top 8 Decks | `/top-8` | Placeholder | Top 8 decks organized by event |
| Statistics | `/stats` | Future | Match statistics and trends |
| Help | `/help` | Future | Help and documentation |

---

## Page Structure

### 1. Home Page (`/`) - Global Leaderboard

**File:** `templates/index.html`

The main landing page displays the global leaderboard.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         [NAVBAR COMPONENT]                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                    Global Leaderboard                                   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Rank │ Player          │ ELO  │ Wins │ Losses │ Win Rate       │   │
│  ├──────┼─────────────────┼──────┼──────┼────────┼────────────────┤   │
│  │ 1    │ PlayerOne       │ 1850 │ 45   │ 12     │ 78.9%          │   │
│  │ 2    │ PlayerTwo       │ 1780 │ 38   │ 15     │ 71.7%          │   │
│  │ ...  │ ...             │ ...  │ ...  │ ...    │ ...            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│                    [Pagination / Load More]                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2. Avatar Winrates Page (`/avatars`)

**File:** `templates/avatars.html` (exists, needs update)

Display win rates grouped by avatar/character.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         [NAVBAR COMPONENT]                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                    Avatar Win Rates                                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ [Avatar Image] │ Avatar Name │ Matches │ Wins │ Win Rate       │   │
│  ├────────────────┼─────────────┼─────────┼──────┼────────────────┤   │
│  │ [Image]        │ Avatar A    │ 156     │ 89   │ 57.1%          │   │
│  │ [Image]        │ Avatar B    │ 142     │ 78   │ 54.9%          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3. ELO Page (`/elo`)

**File:** `templates/elo.html` (new)

Landing page for ELO leaderboards with server selection.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         [NAVBAR COMPONENT]                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                    ELO Leaderboards                                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Select a Server                               │   │
│  │                                                                  │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ Global           │  │ Sorcerers        │                     │   │
│  │  │ Leaderboard      │  │ Summit           │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  │                                                                  │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ Server 2         │  │ Server 3         │                     │   │
│  │  │ (Placeholder)    │  │ (Placeholder)    │                     │   │
│  │  └──────────────────┘  └──────────────────┘                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4. Server-Specific ELO Page (`/elo/server/<guild_id>`)

**File:** `templates/elo_server.html` (new)

Displays leaderboard for a specific server.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         [NAVBAR COMPONENT]                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│         Sorcerers Summit Leaderboard                                    │
│            ← Back to Server Selection                                   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Rank │ Player          │ ELO  │ Wins │ Losses │ Win Rate       │   │
│  ├──────┼─────────────────┼──────┼──────┼────────┼────────────────┤   │
│  │ 1    │ PlayerOne       │ 1850 │ 45   │ 12     │ 78.9%          │   │
│  │ 2    │ PlayerTwo       │ 1780 │ 38   │ 15     │ 71.7%          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5. About Page (`/about`)

**File:** `templates/about.html` (exists, needs navbar update)

### 6. Top 8 Events List Page (`/top-8`)

**File:** `templates/pages/top_8.html` (new)

Displays a list of all events to choose from. Users click an event to see its decks.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         [NAVBAR COMPONENT]                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                    Top 8 Decks by Event                                 │
│                                                                         │
│  Select an event to view decklists:                                    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Event Name                          │ Date       │ Players     │   │
│  ├─────────────────────────────────────┼────────────┼─────────────┤   │
│  │ SCG CON Baltimore 2025              │ 2025-03-15 │ 64          │   │
│  │ Unland Cup 2025                     │ 2025-01-18 │ 48          │   │
│  │ GenCon 2024 Championship            │ 2024-08-03 │ 128         │   │
│  │ Sorcery Fest 2025                   │ 2025-02-22 │ 56          │   │
│  │ TTS League Season 7 Top Cut         │ 2024-12-01 │ 16          │   │
│  │ ...                                 │            │             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7. Event Detail Page (`/top-8/<event_folder>`)

**File:** `templates/pages/event_detail.html` (new)

Displays the Top 8 decks for a specific event, plus all participants if available.

**Deck URL Format:** `https://curiosa.io/decks/{deck_id}`

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         [NAVBAR COMPONENT]                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ← Back to Events                                                       │
│                                                                         │
│         SCG CON Baltimore 2025                                          │
│            Date: March 15, 2025  │  Players: 64                        │
│                                                                         │
│  ─────────────────── TOP 8 ───────────────────                         │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Place  │ Player        │ Avatar        │ Deck                    │   │
│  ├────────┼───────────────┼───────────────┼─────────────────────────┤   │
│  │ 1st    │ UnderSietch   │ Druid         │ [View on Curiosa]       │   │
│  │ 2nd    │ PlayerTwo     │ Geomancer     │ [View on Curiosa]       │   │
│  │ 3rd    │ PlayerThree   │ Avatar of Air │ [View on Curiosa]       │   │
│  │ 4th    │ PlayerFour    │ Rin           │ [View on Curiosa]       │   │
│  │ 5-8th  │ PlayerFive    │ Tetra         │ [View on Curiosa]       │   │
│  │ 5-8th  │ PlayerSix     │ Necromancer   │ [View on Curiosa]       │   │
│  │ 5-8th  │ PlayerSeven   │ Cryomancer    │ [View on Curiosa]       │   │
│  │ 5-8th  │ PlayerEight   │ Druid         │ [View on Curiosa]       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ─────────────────── ALL PARTICIPANTS ───────────────────              │
│  (Shown if full event data available)                                  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Player          │ Avatar          │ Deck                        │   │
│  ├─────────────────┼─────────────────┼─────────────────────────────┤   │
│  │ Player9         │ Pyromancer      │ [View on Curiosa]           │   │
│  │ Player10        │ Druid           │ [View on Curiosa]           │   │
│  │ Player11        │ Avatar of Water │ [View on Curiosa]           │   │
│  │ ...             │ ...             │ ...                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Features:**

- Top 8 table with placement indicators (1st, 2nd, 3rd)
- "View on Curiosa" links to `https://curiosa.io/decks/{id}`
- All Participants table shown below if full event JSON exists
- Back button to return to event list
  └─────────────────────────────────────────────────────────────────────────┘

````

**Features:**
- Events listed in reverse chronological order (newest first)
- Each event card shows event name, date, and player count
- Top 8 players displayed with placement, name, avatar, and deck link
- "View Deck" links to Curiosa or deck detail page
- Collapsible event cards for easier browsing

---

## Component Structure

### Navbar Component

**File:** `templates/components/navbar.html`

```html
<!-- Navbar Component -->
<nav class="navbar">
    <div class="navbar-left">
        <button class="hamburger-btn" id="hamburger-toggle">
            <span class="hamburger-icon">≡</span>
        </button>
        <a href="/" class="brand-link">Sorcerers Summit</a>
    </div>

    <div class="navbar-center">
        <a href="/" class="nav-link">Home</a>
        <a href="https://discord.gg/..." class="nav-link" target="_blank">Discord</a>
        <a href="https://patreon.com/..." class="nav-link" target="_blank">Patreon</a>
        <a href="/about" class="nav-link">About</a>
    </div>

    <div class="navbar-right">
        <!-- Future: User profile/login -->
    </div>
</nav>

<!-- Hamburger Menu Sidebar -->
<aside class="sidebar" id="sidebar">
    <div class="sidebar-header">
        <span>Menu</span>
        <button class="close-btn" id="sidebar-close">✕</button>
    </div>
    <nav class="sidebar-nav">
        <a href="/avatars" class="sidebar-link">Avatar Winrates</a>
        <div class="sidebar-group">
            <span class="sidebar-group-title">ELO Leaderboards</span>
            <a href="/elo" class="sidebar-link sidebar-sublink">All Servers</a>
            <a href="/elo/global" class="sidebar-link sidebar-sublink">Global</a>
        </div>
        <a href="/deck-help" class="sidebar-link">Deck Help</a>
        <a href="/top-8" class="sidebar-link">Top 8 Decks</a>
        <a href="/stats" class="sidebar-link">Statistics</a>
        <a href="/help" class="sidebar-link">Help</a>
    </nav>
</aside>

<!-- Overlay for mobile -->
<div class="sidebar-overlay" id="sidebar-overlay"></div>
````

---

## Folder Structure

The web app will be organized by component, with each component having its own CSS file for component-specific styles while using a global CSS for standardization.

```
web-app/
├── app.py                              # Flask application
├── requirements.txt
├── README.md
│
├── static/
│   ├── css/
│   │   ├── global.css                  # Global styles, variables, resets
│   │   ├── utilities.css               # Utility classes (margins, padding, etc.)
│   │   │
│   │   └── components/                 # Component-specific styles
│   │       ├── navbar.css              # Navbar and sidebar styles
│   │       ├── leaderboard.css         # Leaderboard table styles
│   │       ├── player-card.css         # Player profile card styles
│   │       ├── avatar-grid.css         # Avatar winrates grid styles
│   │       ├── event-card.css          # Top 8 event card styles
│   │       ├── deck-viewer.css         # Deck display styles
│   │       ├── buttons.css             # Button styles
│   │       ├── forms.css               # Form input styles
│   │       └── modals.css              # Modal/popup styles
│   │
│   ├── js/
│   │   ├── main.js                     # Global JavaScript
│   │   │
│   │   └── components/                 # Component-specific scripts
│   │       ├── navbar.js               # Hamburger menu toggle
│   │       ├── leaderboard.js          # Sorting, filtering, pagination
│   │       ├── deck-viewer.js          # Deck display interactions
│   │       └── event-card.js           # Collapsible event cards
│   │
│   └── images/
│       ├── logo/                       # Logo variations
│       ├── avatars/                    # Avatar images
│       └── icons/                      # UI icons
│
└── templates/
    ├── base.html                       # Base template with global CSS imports
    │
    ├── components/                     # Reusable Jinja2 components
    │   ├── navbar.html                 # Top navigation + hamburger sidebar
    │   ├── footer.html                 # Page footer
    │   ├── leaderboard_table.html      # Leaderboard table component
    │   ├── player_card.html            # Player profile card
    │   ├── event_card.html             # Top 8 event card
    │   ├── deck_viewer.html            # Deck display component
    │   └── pagination.html             # Pagination controls
    │
    ├── pages/                          # Full page templates
    │   ├── index.html                  # Home - Global Leaderboard
    │   ├── about.html                  # About page
    │   ├── player.html                 # Player profile page
    │   ├── avatars.html                # Avatar winrates page
    │   ├── elo.html                    # ELO server selection
    │   ├── elo_server.html             # Server-specific leaderboard
    │   ├── deck_help.html              # Deck help page
    │   ├── top_8.html                  # Top 8 decks by event
    │   ├── stats.html                  # Statistics page
    │   └── help.html                   # Help/documentation page
    │
    └── errors/                         # Error page templates
        ├── 404.html                    # Not found
        └── 500.html                    # Server error
```

### CSS Architecture

**Global CSS (`global.css`)** - Loaded on every page:

```css
/* CSS Custom Properties for theming */
:root {
  /* Colors */
  --color-primary: #ffd700;
  --color-secondary: #1a1a2e;
  --color-background: #0f0f1a;
  --color-surface: #16213e;
  --color-text: #ffffff;
  --color-text-muted: #a0a0a0;
  --color-success: #4caf50;
  --color-error: #f44336;

  /* Typography */
  --font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  --font-size-base: 16px;
  --font-size-sm: 0.875rem;
  --font-size-lg: 1.25rem;
  --font-size-xl: 1.5rem;

  /* Spacing */
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;

  /* Border Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;

  /* Shadows */
  --shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.2);
  --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.3);
  --shadow-lg: 0 8px 16px rgba(0, 0, 0, 0.4);

  /* Transitions */
  --transition-fast: 0.15s ease;
  --transition-normal: 0.3s ease;
}

/* CSS Reset */
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  background-color: var(--color-background);
  color: var(--color-text);
  line-height: 1.6;
}

/* Global link styles */
a {
  color: var(--color-primary);
  text-decoration: none;
  transition: color var(--transition-fast);
}

a:hover {
  color: #ffed4a;
}
```

**Component CSS Files** - Each uses global variables:

```css
/* Example: components/leaderboard.css */
.leaderboard {
  background: var(--color-surface);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  overflow: hidden;
}

.leaderboard__header {
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-secondary);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.leaderboard__row {
  display: grid;
  grid-template-columns: 60px 1fr 80px 80px 80px 100px;
  padding: var(--spacing-sm) var(--spacing-lg);
  transition: background var(--transition-fast);
}

.leaderboard__row:hover {
  background: rgba(255, 215, 0, 0.1);
}
```

### Base Template (`base.html`)

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{% block title %}Sorcerers Summit{% endblock %}</title>

    <!-- Global CSS (always loaded) -->
    <link
      rel="stylesheet"
      href="{{ url_for('static', filename='css/global.css') }}" />
    <link
      rel="stylesheet"
      href="{{ url_for('static', filename='css/utilities.css') }}" />
    <link
      rel="stylesheet"
      href="{{ url_for('static', filename='css/components/navbar.css') }}" />

    <!-- Page-specific CSS -->
    {% block styles %}{% endblock %}
  </head>
  <body>
    {% include 'components/navbar.html' %}

    <main class="main-content">{% block content %}{% endblock %}</main>

    {% include 'components/footer.html' %}

    <!-- Global JS -->
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    <script src="{{ url_for('static', filename='js/components/navbar.js') }}"></script>

    <!-- Page-specific JS -->
    {% block scripts %}{% endblock %}
  </body>
</html>
```

### Page Template Example (`pages/top_8.html`)

```html
{% extends 'base.html' %} {% block title %}Top 8 Decks - Sorcerers Summit{%
endblock %} {% block styles %}
<!-- Component CSS for this page -->
<link
  rel="stylesheet"
  href="{{ url_for('static', filename='css/components/event-card.css') }}" />
<link
  rel="stylesheet"
  href="{{ url_for('static', filename='css/components/deck-viewer.css') }}" />
{% endblock %} {% block content %}
<div class="container">
  <h1>Top 8 Decks</h1>

  {% for event in events %} {% include 'components/event_card.html' %} {% endfor
  %}
</div>
{% endblock %} {% block scripts %}
<script src="{{ url_for('static', filename='js/components/event-card.js') }}"></script>
{% endblock %}
```

---

## File Changes Required

### New Files

| File                               | Description                 |
| ---------------------------------- | --------------------------- |
| `templates/components/navbar.html` | Reusable navbar component   |
| `templates/elo.html`               | ELO server selection page   |
| `templates/elo_server.html`        | Server-specific leaderboard |
| `static/css/navbar.css`            | Navbar and sidebar styles   |
| `static/js/navbar.js`              | Hamburger menu toggle logic |

### Files to Modify

| File                     | Changes                                          |
| ------------------------ | ------------------------------------------------ |
| `templates/index.html`   | Add navbar include, update to global leaderboard |
| `templates/about.html`   | Add navbar include                               |
| `templates/avatars.html` | Add navbar include                               |
| `templates/player.html`  | Add navbar include                               |
| `static/css/style.css`   | Add navbar spacing, update layout                |
| `app.py`                 | Add new routes for `/elo`, `/elo/server/<id>`    |

---

## Routes to Add

```python
# app.py additions

@app.route('/elo')
def elo_servers():
    """Display list of servers with ELO leaderboards."""
    servers = get_all_configured_servers()
    return render_template('elo.html', servers=servers)

@app.route('/elo/global')
def elo_global():
    """Display global ELO leaderboard (all servers combined)."""
    leaderboard = get_global_leaderboard()
    return render_template('elo_server.html',
                          server_name="Global",
                          leaderboard=leaderboard)

@app.route('/elo/server/<int:guild_id>')
def elo_server(guild_id):
    """Display ELO leaderboard for a specific server."""
    server = get_server_config(guild_id)
    if not server:
        abort(404)
    leaderboard = get_server_leaderboard(guild_id)
    return render_template('elo_server.html',
                          server_name=server['name'],
                          guild_id=guild_id,
                          leaderboard=leaderboard)
```

---

## Event Management System

### Overview

Events and Top 8 decks are managed using the existing JSON file structure in `web-app/top-8-decks-by-event/`. Each event has its own folder containing deck data.

### Existing Folder Structure

```
web-app/top-8-decks-by-event/
├── UnlandCup25/
│   ├── UnlandCup25Top8.json       # Full deck data with card details
│   ├── UnlandCup25Top8.csv        # CSV export
│   ├── UnlandCup25Top8 elements.csv
│   ├── UnlandCup25.json           # All decks (not just Top 8)
│   └── UnlandCup25.csv
├── GenCon2024Stats/
│   ├── Gencon 2024.json
│   ├── Gencon 2024 card count top 8.csv
│   └── ...
├── SCGCON2025/
├── SorceryFest2025/
├── Gencon2025/
└── ... (18+ events)
```

### Adding Event Metadata

Add an `event.json` file to each event folder with metadata:

```json
// web-app/top-8-decks-by-event/UnlandCup25/event.json
{
  "name": "Unland Cup 2025",
  "date": "2025-01-18",
  "type": "tournament",
  "player_count": 48,
  "location": "Online",
  "bracket_url": "https://challonge.com/unlandcup25",
  "description": "Annual Unland Cup tournament",
  "placements": [
    {
      "placement": 1,
      "player": "Aric",
      "deck_file": "UnlandCup25Top8.json",
      "deck_index": 0
    },
    {
      "placement": 2,
      "player": "PlayerTwo",
      "deck_file": "UnlandCup25Top8.json",
      "deck_index": 1
    },
    {
      "placement": 3,
      "player": "PlayerThree",
      "deck_file": "UnlandCup25Top8.json",
      "deck_index": 2
    }
  ]
}
```

### JSON Deck Format (Current)

Your existing format from Curiosa exports:

```json
[
  {
    "id": "clqed5bul008g71fm1gadl1dm",
    "name": "AOE Earth-Air Midrange",
    "username": "Aric",
    "visibility": "Private",
    "format": "Constructed",
    "legality": { "isLegal": true, "context": "" },
    "avatar": [
      {
        "identifier": "avatar_of_earth",
        "name": "Avatar of Earth",
        "quantity": 1,
        "type": "Avatar",
        "rarity": "Elite",
        ...
      }
    ],
    "spellbook": [
      {
        "identifier": "daperyll_vampire",
        "name": "Daperyll Vampire",
        "quantity": 2,
        "elements": "Air",
        "cost": 5,
        "type": "Minion",
        ...
      }
    ]
  }
]
```

### Alternative Format (GenCon style)

Some events use a different format with player name in key:

```json
[
  {
    "Jake Conner GenCon 2024, 1st, 6-0": {
      "Avatar": [{ "Name": "Geomancer", "Quantity": 1 }],
      "Minion": [{ "Name": "Land Surveyor", "Quantity": 4, "Cost": 2 }],
      ...
    }
  }
]
```

### Event Index File

Create a master index file to list all events:

```json
// web-app/top-8-decks-by-event/events-index.json
{
  "events": [
    {
      "folder": "UnlandCup25",
      "name": "Unland Cup 2025",
      "date": "2025-01-18",
      "type": "tournament",
      "player_count": 48,
      "top8_file": "UnlandCup25Top8.json",
      "format": "curiosa"
    },
    {
      "folder": "GenCon2024Stats",
      "name": "GenCon 2024 Championship",
      "date": "2024-08-03",
      "type": "tournament",
      "player_count": 128,
      "top8_file": "Gencon 2024.json",
      "format": "legacy"
    },
    {
      "folder": "SCGCON2025",
      "name": "SCG CON 2025",
      "date": "2025-03-15",
      "type": "tournament"
    }
  ]
}
```

### Flask Routes for Events

```python
# app.py

import os
import json

EVENTS_DIR = 'top-8-decks-by-event'

def load_events_index():
    """Load the events index file."""
    index_path = os.path.join(EVENTS_DIR, 'events-index.json')
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return json.load(f)
    # Fallback: scan folders and build index dynamically
    return build_events_index_from_folders()

def build_events_index_from_folders():
    """Dynamically build events list from folder names."""
    events = []
    for folder in os.listdir(EVENTS_DIR):
        folder_path = os.path.join(EVENTS_DIR, folder)
        if os.path.isdir(folder_path):
            # Try to load event.json if it exists
            event_json = os.path.join(folder_path, 'event.json')
            if os.path.exists(event_json):
                with open(event_json, 'r') as f:
                    event_data = json.load(f)
                    event_data['folder'] = folder
                    events.append(event_data)
            else:
                # Create basic entry from folder name
                events.append({
                    'folder': folder,
                    'name': folder.replace('Stats', '').replace('_', ' '),
                    'date': None
                })
    return {'events': sorted(events, key=lambda x: x.get('date') or '', reverse=True)}

def load_event_decks(folder, filename=None):
    """Load deck data for an event."""
    folder_path = os.path.join(EVENTS_DIR, folder)
    all_files = os.listdir(folder_path)

    top8_decks = None
    all_decks = None

    # Find Top 8 JSON file
    for f in all_files:
        if f.endswith('.json') and ('top8' in f.lower() or 'top 8' in f.lower()):
            with open(os.path.join(folder_path, f), 'r') as file:
                top8_decks = json.load(file)
            break

    # Find full event JSON (all participants)
    for f in all_files:
        if f.endswith('.json') and 'top8' not in f.lower() and 'top 8' not in f.lower():
            with open(os.path.join(folder_path, f), 'r') as file:
                all_decks = json.load(file)
            break

    # If no separate top8 file, use first 8 from all_decks
    if not top8_decks and all_decks:
        top8_decks = all_decks[:8]

    return {
        'top8': top8_decks or [],
        'all_participants': all_decks or []
    }

def build_curiosa_url(deck_id):
    """Build Curiosa deck URL from deck ID."""
    return f"https://curiosa.io/decks/{deck_id}"

@app.route('/top-8')
def top_8_events():
    """Display list of all events to choose from."""
    events_data = load_events_index()
    return render_template('pages/top_8.html', events=events_data['events'])

@app.route('/top-8/<folder>')
def event_details(folder):
    """Display Top 8 decks and all participants for a specific event."""
    events_data = load_events_index()
    event = next((e for e in events_data['events'] if e['folder'] == folder), None)
    if not event:
        abort(404)

    deck_data = load_event_decks(folder)

    # Normalize decks to standard format
    top8 = [normalize_deck(d) for d in deck_data['top8']]
    all_participants = [normalize_deck(d) for d in deck_data['all_participants']]

    # Remove top 8 from all_participants to avoid duplicates
    top8_ids = {d.get('id') for d in deck_data['top8'] if d.get('id')}
    remaining_participants = [
        normalize_deck(d) for d in deck_data['all_participants']
        if d.get('id') not in top8_ids
    ]

    return render_template('pages/event_detail.html',
                          event=event,
                          top8=top8,
                          all_participants=remaining_participants,
                          build_curiosa_url=build_curiosa_url)
```

### Adding a New Event

**Step 1:** Create folder in `web-app/top-8-decks-by-event/`

```
NewEvent2026/
```

**Step 2:** Add deck JSON (export from Curiosa or create manually)

```
NewEvent2026/NewEvent2026Top8.json    # Top 8 decks only
NewEvent2026/NewEvent2026.json         # All participants (optional)
```

**Step 3:** (Optional) Add event.json with metadata

```json
{
  "name": "New Event 2026",
  "date": "2026-02-15",
  "type": "tournament",
  "player_count": 32
}
```

**Step 4:** (Optional) Update events-index.json or let the app auto-discover

### Deck Normalization

The deck normalizer extracts key info and builds Curiosa URLs:

```python
CURIOSA_BASE_URL = "https://curiosa.io/decks/"

def normalize_deck(deck_data, format_type='curiosa'):
    """Normalize deck data to a standard format for display."""
    if format_type == 'curiosa' or 'id' in deck_data:
        # Standard Curiosa export format
        deck_id = deck_data.get('id', '')
        return {
            'id': deck_id,
            'deck_url': f"{CURIOSA_BASE_URL}{deck_id}" if deck_id else None,
            'name': deck_data.get('name', 'Unknown Deck'),
            'player': deck_data.get('username', 'Unknown'),
            'avatar': deck_data['avatar'][0]['name'] if deck_data.get('avatar') else 'Unknown',
            'cards': deck_data.get('spellbook', []),
            'card_count': sum(c.get('quantity', 0) for c in deck_data.get('spellbook', []))
        }
    else:
        # Handle "Player Name, 1st, 6-0" format (legacy)
        key = list(deck_data.keys())[0]
        player_info = key.split(',')
        cards = deck_data[key]
        return {
            'id': None,
            'deck_url': None,
            'name': f"{player_info[0]}'s Deck",
            'player': player_info[0].strip(),
            'placement': player_info[1].strip() if len(player_info) > 1 else None,
            'avatar': cards.get('Avatar', [{}])[0].get('Name', 'Unknown'),
            'cards': cards,
            'card_count': sum(c.get('Quantity', 0) for cat in cards.values() for c in cat)
        }
```

### Event Detail Template

```html
<!-- templates/pages/event_detail.html -->
{% extends 'base.html' %} {% block title %}{{ event.name }} - Top 8 Decks{%
endblock %} {% block styles %}
<link
  rel="stylesheet"
  href="{{ url_for('static', filename='css/components/event-card.css') }}" />
{% endblock %} {% block content %}
<div class="container">
  <a href="{{ url_for('top_8_events') }}" class="back-link">← Back to Events</a>

  <h1>{{ event.name }}</h1>
  {% if event.date or event.player_count %}
  <p class="event-meta">
    {% if event.date %}Date: {{ event.date }}{% endif %} {% if event.date and
    event.player_count %} │ {% endif %} {% if event.player_count %}Players: {{
    event.player_count }}{% endif %}
  </p>
  {% endif %}

  <!-- TOP 8 TABLE -->
  <h2>Top 8</h2>
  <table class="decks-table">
    <thead>
      <tr>
        <th>Place</th>
        <th>Player</th>
        <th>Avatar</th>
        <th>Deck</th>
      </tr>
    </thead>
    <tbody>
      {% for deck in top8 %}
      <tr>
        <td>
          {% if loop.index == 1 %}1st {% elif loop.index == 2 %}2nd {% elif
          loop.index == 3 %}3rd {% elif loop.index == 4 %}4th {% else %}5-8th {%
          endif %}
        </td>
        <td>{{ deck.player }}</td>
        <td>{{ deck.avatar }}</td>
        <td>
          {% if deck.deck_url %}
          <a href="{{ deck.deck_url }}" target="_blank" class="deck-link">
            View on Curiosa 🔗
          </a>
          {% else %}
          <span class="no-link">N/A</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <!-- ALL PARTICIPANTS TABLE (if available) -->
  {% if all_participants %}
  <h2>All Participants</h2>
  <table class="decks-table">
    <thead>
      <tr>
        <th>Player</th>
        <th>Avatar</th>
        <th>Deck</th>
      </tr>
    </thead>
    <tbody>
      {% for deck in all_participants %}
      <tr>
        <td>{{ deck.player }}</td>
        <td>{{ deck.avatar }}</td>
        <td>
          {% if deck.deck_url %}
          <a href="{{ deck.deck_url }}" target="_blank" class="deck-link">
            View on Curiosa 🔗
          </a>
          {% else %}
          <span class="no-link">N/A</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>
{% endblock %}
```

---

## CSS Structure

### Navbar Styles (`static/css/navbar.css`)

```css
/* Navbar */
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #1a1a2e;
  padding: 0.75rem 1.5rem;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.hamburger-btn {
  background: none;
  border: none;
  color: white;
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0.5rem;
}

.brand-link {
  font-size: 1.25rem;
  font-weight: bold;
  color: #ffd700;
  text-decoration: none;
}

.navbar-center {
  display: flex;
  gap: 2rem;
}

.nav-link {
  color: white;
  text-decoration: none;
  transition: color 0.2s;
}

.nav-link:hover {
  color: #ffd700;
}

/* Sidebar */
.sidebar {
  position: fixed;
  top: 0;
  left: -280px;
  width: 280px;
  height: 100vh;
  background: #16213e;
  z-index: 1100;
  transition: left 0.3s ease;
  overflow-y: auto;
}

.sidebar.open {
  left: 0;
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1050;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.3s, visibility 0.3s;
}

.sidebar-overlay.visible {
  opacity: 1;
  visibility: visible;
}

/* Responsive */
@media (max-width: 768px) {
  .navbar-center {
    display: none;
  }
}
```

---

## Implementation Priority

### Phase 1 - MVP

1. [ ] Create navbar component
2. [ ] Add hamburger menu with sidebar
3. [ ] Update index.html to global leaderboard
4. [ ] Include navbar in all existing pages
5. [ ] Basic responsive styling

### Phase 2 - ELO Pages

6. [ ] Create `/elo` server selection page
7. [ ] Create `/elo/server/<id>` template
8. [ ] Add routes to app.py
9. [ ] Connect to database for server list

### Phase 3 - Polish

10. [ ] Update avatars page styling
11. [ ] Add loading states
12. [ ] Mobile optimization
13. [ ] Add animations/transitions

---

## External Links

| Link    | URL                              | Notes                     |
| ------- | -------------------------------- | ------------------------- |
| Discord | `https://discord.gg/YOUR_INVITE` | Update with actual invite |
| Patreon | `https://patreon.com/YOUR_PAGE`  | Update with actual page   |

---

## Notes

- Use Jinja2 `{% include %}` for navbar component
- Consider using Flask-Assets for CSS/JS bundling
- Test hamburger menu on mobile devices
- Ensure accessibility (keyboard navigation, ARIA labels)
- Use CSS custom properties for theming consistency
