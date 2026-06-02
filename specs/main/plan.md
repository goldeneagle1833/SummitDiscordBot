# Implementation Plan: Top-8 Events Page Redesign

**Branch**: `main` | **Date**: 2026-06-01 | **Spec**: User feedback (Discord conversation)
**Input**: User feedback from Zuul and GoldenEagle1833 about Events page UX issues

## Summary

Redesign the Top-8 Events page (`Events.jsx`) to improve readability and user experience. Key changes: remove confusing star ratings, add event date and deck count to cards, sort by most recent date, add a featured "Most Recent Event" hero section, show the winning avatar on each event card, and clean up event names with better formatting.

## Technical Context

**Language/Version**: Python 3.11+ (Flask backend), React 18 (Vite frontend)
**Primary Dependencies**: Flask, React, Tailwind CSS, Curiosa API (avatar images)
**Storage**: JSON files in `web-app/top-8-decks-by-event/` + `_event_metadata.json`
**Testing**: pytest (backend 73+ tests), Vitest (frontend 61+ tests)
**Target Platform**: Web (desktop + mobile responsive)
**Project Type**: Full-stack web application (Flask API + React SPA)
**Performance Goals**: No new API calls on page load beyond existing `GET /api/top-8-events`
**Constraints**: Must not break admin drag-reorder or event create/edit workflows
**Scale/Scope**: ~30-40 events, purely frontend-driven changes with minor backend data additions

## Constitution Check

*GATE: No project constitution defined (template only). Proceeding without gate enforcement.*

No violations — the constitution is unpopulated (template placeholders only).

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # Phase 1 output
    └── api-changes.md   # API response shape changes
```

### Source Code (repository root)

```text
web-app/
├── frontend/src/
│   ├── pages/Events.jsx           # PRIMARY: Redesigned event listing page
│   └── api/events.js              # Minor: no changes expected
├── repositories/events.py         # MODIFIED: Add event_date + winner avatar to response
├── routes/api/events.py           # MINOR: Pass new fields through
└── utils/formatting.py            # MINOR: Date extraction improvements
```

**Structure Decision**: This is a UI-focused redesign within the existing web app structure. No new files needed — modifications to existing components and backend response shapes.

## Complexity Tracking

No violations to justify.

---

## Changes Summary

### 1. Remove Stars (Rating System)
**Problem**: Stars (1-3 rating) are meaningless to users — no tooltip, no legend, no explanation.
**Solution**: Remove stars from event cards entirely. Keep `rating` field in metadata for admin use (event tier for potential future use) but don't display it on cards.

### 2. Add Event Date to Cards
**Problem**: No date shown on event cards. Users can't tell when events happened.
**Solution**: Extract date from event folder name (already contains date info like `2026 4 4`) and/or from the deck JSON data. Display formatted date on each card (e.g., "Apr 4, 2026").
**Backend change**: Add `event_date` field to the `get_all_events()` response.

### 3. Sort by Most Recent Date (Default)
**Problem**: Current sort is by year (coarse) or custom admin order.
**Solution**: Default sort by extracted date descending (most recent first). Admin custom order still overrides when set.

### 4. Featured "Most Recent Event" Hero Section
**Problem**: Page is a uniform grid — monotonous, no visual hierarchy.
**Solution**: Add a large featured card at the top for the most recent event. Shows event name, date, deck count, and winner's avatar/deck info. Visually distinct from the grid below.

### 5. Show Winning Avatar on Event Cards
**Problem**: Cards are plain text with no visual interest.
**Solution**: Display the 1st-place avatar name as a badge on each event card. Optionally show avatar image if available from Curiosa CDN.
**Backend change**: Add `winner_avatar` and `winner_name` fields to event list response (extracted from first deck in top8 JSON).

### 6. Improved Event Name Formatting
**Problem**: Names derived from folder names are "jank" — inconsistent formatting, raw dates embedded.
**Solution**: Better `format_event_name()` logic to separate event name from date. Display name and date on separate lines in the card. Allow admin override via existing edit modal.

### 7. Card Layout Redesign
**Current**: Name, stars, deck count, "Top 8 Available" badge
**New**:
```
┌─────────────────────────────┐
│ [Avatar Badge]   Apr 4, 2026│
│                              │
│ Ascanrask III                │
│                              │
│ Winner: Dado (Necromancer)   │
│ 24 decks                     │
└─────────────────────────────┘
```
