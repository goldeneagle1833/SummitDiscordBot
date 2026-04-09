# Implementation Plan: Fun Stats Page

**Branch**: `main` | **Date**: 2026-04-08 | **Spec**: `specs/main/spec.md`
**Input**: User request for a new "Fun Stats" web page with event filtering and community stats

## Summary

A new public-facing "Fun Stats" page for the web app that showcases entertaining community statistics: win streaks, most diverse players, most active players, biggest upsets, nemesis pairs, and more. The page reuses the event/source filter pattern from the avatar winrate page and is added to the hamburger sidebar menu. All data is read-only from existing `match_records`, `match_records_archive`, and `elo.db` tables — no schema changes required.

## Technical Context

**Language/Version**: Python 3.11+ (Flask backend), HTML/CSS/JS (Jinja2 templates)
**Primary Dependencies**: Flask, SQLite3, Jinja2
**Storage**: SQLite (`match_records.db`, `elo.db`) — read-only queries
**Testing**: Manual browser testing + syntax/import verification
**Target Platform**: Linux server (production), Windows (development)
**Project Type**: Web application (Flask)
**Performance Goals**: Page load < 2s, API response < 1s
**Constraints**: Discord's existing database schema — no writes, no migrations
**Scale/Scope**: Single page with 1 route, 1 API blueprint, 1 template, 1 CSS, 1 JS

## Constitution Check

*GATE: Constitution is a placeholder template — no project-specific gates defined. Proceeding with established codebase patterns.*

The project follows these observed conventions:
- **Routes pattern**: Page route in `pages.py`, API routes in `routes/api/` blueprint
- **Template pattern**: Jinja2 templates in `templates/pages/`, extend `base.html`
- **Database access**: Direct SQLite connections (no ORM), connections opened/closed per function
- **Event filtering**: Query `events` table for metadata, filter `match_records` by timestamp range
- **Navigation**: Sidebar links in `templates/components/navbar.html`

All conventions will be followed.

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── fun-stats-api.md
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
web-app/
├── routes/
│   ├── pages.py                    # ADD: /fun-stats route
│   └── api/
│       └── fun_stats.py            # NEW: Fun stats API blueprint
├── templates/
│   ├── components/
│   │   └── navbar.html             # EDIT: Add "Fun Stats" link to sidebar
│   └── pages/
│       └── fun_stats.html          # NEW: Fun Stats page template
└── static/
    ├── css/pages/
    │   └── fun-stats.css           # NEW: Page-specific styles
    └── js/pages/
        └── fun-stats.js            # NEW: Filter logic + API calls + rendering
```

**Structure Decision**: Follows the existing web app convention — a page route, an API blueprint, a Jinja2 template, and page-specific CSS/JS.

## Stats Breakdown

### User-Requested Stats

| # | Stat | Description | Data Source |
|---|------|-------------|-------------|
| 1 | **Win Streaks** | Best all-time + current active win streak per player (top 10) | All matches ordered by timestamp, iterate tracking consecutive wins |
| 2 | **Most Diverse Player** | Top 10 players who have played the most unique avatars | `json_deck_data_winner`/`json_deck_data_loser` → extract avatar name per match |
| 3 | **Most Active Player** | Top 10 players by total games played | Count appearances as winner + loser |

### Suggested Additional Stats

| # | Stat | Description | Data Source |
|---|------|-------------|-------------|
| 4 | **Biggest Upset** | Match where lower-rated player beat higher-rated player by largest ELO gap (shows both players, result, ELO delta) | `winner_elo_change` / `loser_elo_change` from match records |
| 5 | **Nemesis Pairs** | Top 5 player pairs who have faced each other the most (shows matchup record) | Count matchups between `winner_id`/`losser_id` pairs |
| 6 | **First Player Advantage** | Overall win rate when going first vs second | `winner_went_first` column analysis |
| 7 | **Match Duration Stats** | Average, fastest, and longest match times | `match_time` column (minutes) |
| 8 | **Most Improved** | Top 5 players with biggest cumulative ELO gain in the period | Sum of `winner_lifetime_elo_change` and `loser_lifetime_elo_change` per player |
| 9 | **Ironman Streak** | Players with the most consecutive days containing at least one match | Timestamp analysis for daily activity |

## Implementation Approach

### Backend (API)

1. **New blueprint**: `fun_stats_bp` in `routes/api/fun_stats.py`
2. **Single endpoint**: `GET /api/fun-stats` with optional `?event=<value>&source=<value>` query params
3. **Filter logic**: Reuse the exact pattern from `avatars.py` — `_get_event_date_range()` for event→date mapping, `_collect_rows()` for table selection (current vs archive)
4. **Streak computation**: Port the proven algorithm from `admin.py:516-563` (iterate chronological matches, track current/best per player)
5. **Avatar diversity**: Use `_extract_avatar_from_deck()` pattern from `avatars.py:115-125` to parse JSON deck data

### Frontend (Template + JS)

1. **Template**: Extends `base.html`, includes filter bar (event + source dropdowns) matching avatar page pattern
2. **JavaScript**: On filter change → fetch `/api/fun-stats?event=X&source=Y` → render stat cards
3. **Layout**: Card-based grid layout — each stat gets a card with a title, icon, and ranked list or single value
4. **Responsive**: 1-column mobile, 2-column tablet, 3-column desktop (CSS grid)

### Navigation

1. **Sidebar**: Add `<a href="/fun-stats">Fun Stats</a>` link after "Element Winrates" in `navbar.html`
2. **Public access**: No admin check required — visible to all users

## Complexity Tracking

> No constitution violations. Feature follows established patterns entirely.

| Decision | Rationale |
|----------|-----------|
| Single API endpoint (not per-stat) | All stats share the same filter params and DB connections — one round-trip is simpler and faster |
| Port admin streak logic (not import) | Admin code is tightly coupled to its UNION helpers — cleaner to adapt the algorithm in the new blueprint |
| Client-side rendering | Matches the avatar page pattern — template provides skeleton, JS fills data from API |
