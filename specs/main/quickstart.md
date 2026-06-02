# Quickstart: Top-8 Events Page Redesign

## What This Feature Does

Redesigns the Events/Top-8 listing page to be more readable and user-friendly:
1. Removes confusing star ratings from event cards
2. Adds event dates and sorts by most recent
3. Shows winning player + avatar on each card
4. Adds a featured "Latest Event" hero section at top
5. Cleans up event names (separates name from date)

## Files to Modify

### Backend (3 files)
1. **`web-app/utils/formatting.py`** — Add `extract_date_from_name()` and `strip_date_from_name()`
2. **`web-app/repositories/events.py`** — Extend `get_all_events()` to return new fields (date, winner info), update sort logic
3. **`web-app/routes/api/events.py`** — Pass `event_date` through metadata update endpoint

### Frontend (1 file)
4. **`web-app/frontend/src/pages/Events.jsx`** — Redesign card layout, add featured event section, remove stars

## Implementation Order

1. Add date extraction utilities to `formatting.py`
2. Extend `EventRepository.get_all_events()` with new fields + date-based sorting
3. Update metadata endpoint to accept `event_date` override
4. Redesign `Events.jsx` UI (featured section + card layout + remove stars)
5. Update tests

## How to Test

```bash
# Backend tests
cd web-app && pytest tests/ -v

# Frontend tests
cd web-app/frontend && npm test

# Manual verification
cd web-app && python app.py  # Start Flask on port 5000
cd web-app/frontend && npm run dev  # Start Vite on port 5173
# Visit http://localhost:5173/top-8
```

## Key Design Decisions

- **Stars stay in metadata** — `rating` field preserved in `_event_metadata.json` and admin edit modal, just not shown on cards
- **Date parsing is best-effort** — Some folder names won't parse (e.g., "OchoaDecklists"); these get `null` dates and sort last
- **Admin date override** — New `event_date` field in metadata for unparseable events
- **Winner data from existing JSON** — No new API calls; extracted from first entry in top8 JSON at read time
- **Featured event = first in list** — After date sorting, `filtered[0]` is the featured event; no separate data source
