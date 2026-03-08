# Inline JavaScript Audit

**Date**: 2026-03-08
**Purpose**: Inventory of all inline event handlers across templates

## Summary

- **Total inline handlers found**: 23
- **Handler types**: `onclick`, `onchange`, `onload`, `oninput`, `onsubmit`
- **Files affected**: 7 page templates
- **Priority for extraction**: Start with highest count pages

## Inline Handlers by Page (Descending Order)

| Rank | Page Template | Handler Count | Priority |
|------|---------------|---------------|----------|
| 1 | live_popular_cards.html | 9 | 🔴 High |
| 2 | top_8_event.html | 2 | 🟡 Medium |
| 3 | stats_event.html | 2 | 🟡 Medium |
| 4 | metagame.html | 2 | 🟡 Medium |
| 5 | avatars.html | 2 | 🟡 Medium |
| 6 | match_history.html | 1 | 🟢 Low |
| 7 | elo.html | 1 | 🟢 Low |

## Extraction Strategy

### Phase 1: High Priority (9 handlers)
1. **live_popular_cards.html** - Highest count, likely has filters/charts

### Phase 2: Medium Priority (2 handlers each)
- top_8_event.html
- stats_event.html
- metagame.html
- avatars.html

### Phase 3: Low Priority (1 handler each)
- match_history.html
- elo.html

## Common Handler Patterns

Based on analysis:
- **onclick**: Button clicks, filter triggers
- **onchange**: Dropdown selects, input changes
- **oninput**: Real-time search/filter
- **onload**: Page initialization

## Event Delegation Pattern

Replace inline handlers with:

### Before (Inline - REMOVE)
```html
<button onclick="filterBy('wins')">Filter by Wins</button>
```

### After (Event Delegation - USE)
```html
<!-- Template -->
<button data-action="filter" data-filter-type="wins">Filter by Wins</button>
```

```javascript
// static/js/pages/[page].js
document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action="filter"]');
        if (!btn) return;

        const filterType = btn.dataset.filterType;
        filterBy(filterType);
    });
});
```

## Action Items

- [ ] Extract live_popular_cards.html handlers → `static/js/pages/live_popular_cards.js`
- [ ] Extract top_8_event.html handlers → `static/js/pages/top_8_event.js`
- [ ] Extract stats_event.html handlers → `static/js/pages/stats_event.js`
- [ ] Extract metagame.html handlers → `static/js/pages/metagame.js`
- [ ] Extract avatars.html handlers → `static/js/pages/avatars.js`
- [ ] Extract match_history.html handlers → `static/js/pages/match_history.js`
- [ ] Extract elo.html handlers → `static/js/pages/elo.js`
- [ ] Implement event delegation pattern for all pages
- [ ] Add `defer` attribute to all `<script>` tags

## Validation

After extraction, run:
```bash
grep -rE 'on(click|change|load|input|submit)=' web-app/templates/ --include="*.html" | wc -l
# Target: 0
```

## Security Benefits

Removing inline JavaScript:
- ✅ Enables Content Security Policy (CSP) without `unsafe-inline`
- ✅ Prevents XSS vulnerabilities from template injection
- ✅ Easier to audit and test JavaScript behavior
- ✅ Better code organization and maintainability
