# Inline Styles Audit

**Date**: 2026-03-08
**Purpose**: Inventory of all inline `style=` attributes across templates

## Summary

- **Total inline styles found**: 182
- **Files affected**: 25+ page templates
- **Priority for extraction**: Start with highest count pages

## Inline Styles by Page (Descending Order)

| Rank | Page Template | Inline Style Count | Priority |
|------|---------------|-------------------|----------|
| 1 | player.html | 35 | 🔴 High |
| 2 | elo.html | 25 | 🔴 High |
| 3 | index.html | 20 | 🔴 High |
| 4 | avatars.html | 20 | 🔴 High |
| 5 | metagame.html | 18 | 🟡 Medium |
| 6 | live_popular_cards.html | 9 | 🟡 Medium |
| 7 | elements.html | 9 | 🟡 Medium |
| 8 | admin_audit_log.html | 7 | 🟡 Medium |
| 9 | top_8_event.html | 6 | 🟢 Low |
| 10 | stats_event.html | 5 | 🟢 Low |
| 11 | error.html | 4 | 🟢 Low |
| 12 | match_history.html | 3 | 🟢 Low |
| 13 | fart_leaderboard.html | 3 | 🟢 Low |
| 14 | community.html | 3 | 🟢 Low |
| 15 | cards.html | 3 | 🟢 Low |

## Extraction Strategy

### Phase 1: High Priority Pages (35-20 inline styles)
1. **player.html** (35 styles) - Largest file, highest impact
2. **elo.html** (25 styles) - Core feature page
3. **index.html** (20 styles) - Landing page
4. **avatars.html** (20 styles) - Avatar statistics

**Strategy**: Extract sequentially with visual validation after each

### Phase 2: Medium Priority Pages (18-7 inline styles)
1. metagame.html (18)
2. live_popular_cards.html (9)
3. elements.html (9)
4. admin_audit_log.html (7)

**Strategy**: Can parallelize after Phase 1 patterns established

### Phase 3: Low Priority Pages (≤6 inline styles)
All remaining pages can be parallelized (low risk, simple extractions)

## Common Inline Style Patterns

Based on grep analysis, common patterns include:
- Positioning: `margin`, `padding`, `display`
- Sizing: `width`, `height`, `max-width`
- Colors: `background`, `color`, `border-color`
- Layout: `flex`, `grid`, `justify-content`, `align-items`

## Action Items

- [ ] Extract player.html styles → `static/css/pages/player.css`
- [ ] Extract elo.html styles → `static/css/pages/elo.css`
- [ ] Extract index.html styles → `static/css/pages/index.css`
- [ ] Extract avatars.html styles → `static/css/pages/avatars.css`
- [ ] Identify repeated patterns → move to utilities
- [ ] Document dynamic styles (Jinja2 variables) → use CSS custom properties

## Validation

After extraction, run:
```bash
grep -r 'style=' web-app/templates/ --include="*.html" | wc -l
# Target: 0 (or only approved dynamic exceptions)
```
