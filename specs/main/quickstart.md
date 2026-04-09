# Quickstart: Fun Stats Page

## What This Feature Does

Adds a new "Fun Stats" page to the web app accessible from the hamburger sidebar menu. The page displays entertaining community statistics — win streaks, most diverse players, most active players, biggest upsets, nemesis pairs, first player advantage, match duration stats, most improved players, and ironman streaks. Users can filter all stats by event and match source using the same dropdown pattern as the avatar winrate page.

## Files to Create

| File | Purpose |
|------|---------|
| `web-app/routes/api/fun_stats.py` | Flask API blueprint — computes and returns all stats as JSON |
| `web-app/templates/pages/fun_stats.html` | Jinja2 page template — filter bar + stat card grid skeleton |
| `web-app/static/css/pages/fun-stats.css` | Page-specific styles for stat cards and grid layout |
| `web-app/static/js/pages/fun-stats.js` | Filter logic, API calls, DOM rendering |

## Files to Edit

| File | Change |
|------|--------|
| `web-app/routes/pages.py` | Add `/fun-stats` page route |
| `web-app/templates/components/navbar.html` | Add "Fun Stats" link to sidebar menu |
| `web-app/app.py` | Register the `fun_stats_bp` blueprint |

## Architecture

```
User visits /fun-stats
  → pages.py renders fun_stats.html (empty skeleton + filter bar)
  → fun-stats.js fetches /api/fun-stats/filters (events + sources)
  → fun-stats.js fetches /api/fun-stats (default: current data)
  → JS renders stat cards into the grid

User changes filter
  → fun-stats.js fetches /api/fun-stats?event=X&source=Y
  → JS re-renders all stat cards with new data
```

## Key Patterns to Follow

1. **Event filtering**: Copy the pattern from `routes/api/avatars.py` — `_get_event_date_range()`, query param handling, archive vs current table selection
2. **Win streaks**: Port the algorithm from `routes/api/admin.py:516-563` — chronological iteration tracking current/best per player
3. **Avatar extraction**: Use the JSON parsing pattern from `avatars.py:115-125` — `json.loads(deck_str)["avatar"][0]["name"]`
4. **Blueprint registration**: Follow existing pattern in `app.py` — `from routes.api.fun_stats import fun_stats_bp` then `app.register_blueprint(fun_stats_bp, url_prefix="/api")`
5. **Template structure**: Extend `base.html`, load page-specific CSS/JS blocks
6. **Sidebar link**: Add after "Element Winrates" in `navbar.html`, same styling as other links

## Database Access

- **Read-only** — no writes to any table
- **Two databases**: `match_records.db` (matches) and `elo.db` (events, standings)
- **Connection pattern**: Open/close per function, same as all existing routes
- **Config imports**: `from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH, SEASON_FILTERS`

## Not in Scope

- Admin-only restrictions (page is public)
- Caching/precomputation
- Export/download stats
- Player-specific fun stats (use existing player profile page for that)
