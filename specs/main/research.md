# Research: Top-8 Events Page Redesign

## R1: How to Extract Event Dates

**Decision**: Extract date from folder name patterns, with metadata override fallback.

**Rationale**: Event folder names already contain date information in various formats:
- `Ascanrask III 2026 4 4` -> April 4, 2026
- `Assorted Animals Tournament Grounds 5_19_2026` -> May 19, 2026
- `Aus Store Championship 3 28 2026` -> March 28, 2026
- `Cold Foil Heros 3 30 2026` -> March 30, 2026
- `LinCon May 14-16 2026` -> May 14, 2026
- `GenCon2024Stats` -> 2024 (year only)
- `CortCup2024Stats` -> 2024 (year only)

**Approach**: Add a new `extract_date_from_name()` function in `utils/formatting.py` that returns an ISO date string (or year-only string) by matching common patterns:
1. `YYYY M D` or `YYYY M_D` (space/underscore separated)
2. `M D YYYY` or `M_D_YYYY`
3. `Month D YYYY` or `Month D-D YYYY`
4. Fallback: year-only from existing `extract_year_from_name()`

Allow `_event_metadata.json` overrides via a new `event_date` field for events where folder name doesn't contain parseable dates.

**Alternatives considered**:
- Parse from deck JSON `name` field — unreliable, inconsistent naming
- Require admin to set date manually — too much friction
- Use file modification time — unreliable (files get re-saved)

---

## R2: How to Get Winner Avatar Data

**Decision**: Extract from first deck object in top8 JSON file at event list load time.

**Rationale**: The top8 JSON files are already loaded to count `player_count`. The first entry is always 1st place. Each deck has an `avatar` array with a single object containing `name` and `identifier` fields, plus `username` for the player name.

**Data available per deck**:
- `avatar[0].name` — e.g., "Necromancer"
- `avatar[0].identifier` — e.g., "necromancer" (usable for image URL)
- `username` — e.g., "Dado" (the player who won)

**Avatar images**: Curiosa CDN serves card images. The existing codebase uses avatar identifiers on other pages (Avatar Win Rate page). Can construct image URL from identifier.

**Performance**: Minimal overhead — we already read the JSON to get deck count. Just extract 3 extra fields from `data[0]`.

**Alternatives considered**:
- Pre-cache winner info in metadata JSON — extra maintenance, data already in deck files
- Show avatar image as card background — "might be a bit busy" per user feedback; use small badge instead

---

## R3: What to Replace Stars With

**Decision**: Remove stars from event cards entirely. Replace with winner avatar badge and event date.

**Rationale**: Per user feedback:
- "What are the stars? that doesn't really make sense as a user and never have"
- "You could have the winning deck in the tile instead of the stars"

Stars represent event tier (Major=3, Regional=2, Local=1) based on `EVENT_RATINGS` in `webapp_config.py`, but this is never explained to users.

The `rating` field stays in `_event_metadata.json` and admin edit modal for potential future use, but is not rendered on event cards.

**Alternatives considered**:
- Add tooltip explaining tier system — still visually confusing
- Replace with tier labels ("Major Event") — adds clutter without value
- Keep stars + add labels — half-measure

---

## R4: Featured Event Section Design

**Decision**: Large hero-style card at top of page for the most recent event.

**Rationale**: Per user feedback:
- "Maybe add a big tile up top for Most recent tournament results too to break up the monotony"
- "Yeah having a recent event section is high on the list"

**Design**: Full-width card above the grid showing:
- Event name (larger text)
- Formatted date
- Deck/player count
- Winner name + avatar name/badge
- Direct link to event detail page
- Visually distinct: accent border, slightly different background

No separate API call needed — the featured event is `events[0]` after date sorting (most recent). If admin custom order is set, use that order's first event instead.

---

## R5: Event Name Cleanup

**Decision**: Separate event name from date in display. Improve formatting.

**Current problems**:
- Folder names used when no override: "Ascanrask III 2026 4 4"
- Dates embedded in names make them long and awkward
- `format_event_name()` only does `replace("_", " ").title()`

**Approach**:
1. Strip recognized date patterns from the display name (since date is now shown separately)
2. Add more name mappings to `EVENT_NAME_MAPPINGS` for common events
3. Enhance `format_event_name()` to clean up trailing numbers/dates
4. Admin override via existing edit modal still works

Per user feedback: "some breaking in the tile of name and date" — show name and date on separate lines.

---

## R6: Default Sort Order

**Decision**: Sort by extracted full date descending (most recent first). Admin custom order overrides.

**Rationale**: User feedback: "Order them by recent date." Current year-only sort is too coarse — events from the same year aren't ordered by month/day.

**Implementation**: Enhance `get_all_events()` to use `extract_date_from_name()` for sort key instead of just `extract_year_from_name()`. Events with only year info sort after events with full dates from the same year. Custom order (`_event_order.json`) still takes priority.

---

## Summary

| # | Topic | Decision |
|---|-------|----------|
| R1 | Date extraction | Parse from folder name patterns + metadata override |
| R2 | Winner data | Extract avatar/username from first deck in top8 JSON |
| R3 | Stars removal | Remove from cards, keep in metadata for admin |
| R4 | Featured event | Hero card for most recent, no new API calls |
| R5 | Name cleanup | Separate name from date, improve formatting |
| R6 | Sort order | Full date descending, admin order overrides |
