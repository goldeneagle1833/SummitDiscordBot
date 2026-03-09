# Frontend Refactoring Guide

**Purpose**: Step-by-step guide for refactoring pages to eliminate inline styles and JavaScript
**Created**: 2026-03-08
**Status**: Foundation Complete - Ready for Page Refactoring

## Quick Reference

✅ **Phase 1 & 2 Complete**: Foundation is ready
- Directory structure created
- Base CSS/JS files created
- All page CSS/JS placeholder files created
- `base.html` updated with proper load order

📋 **Next Steps**: Refactor individual pages following this guide

---

## Refactoring Workflow

### For Each Page (Repeat for all 25 pages)

#### Step 1: Convert to base.html (if standalone)

**If page has its own `<html><head>` tags**:

```html
<!-- BEFORE (standalone page like player.html) -->
<!doctype html>
<html lang="en">
  <head>
    <title>Player Profile</title>
    <link rel="stylesheet" href="...tailwind.css">
    <link rel="stylesheet" href="...global.css">
    <!-- ... more CSS ... -->
  </head>
  <body>
    {% include 'components/navbar.html' %}
    <main>
      <!-- Page content -->
    </main>
  </body>
</html>
```

```html
<!-- AFTER (extends base.html) -->
{% extends "base.html" %}

{% block title %}Player Profile - Sorcerers Summit{% endblock %}

{% block styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/player.css') }}?v={{ app_version }}">
{% endblock %}

{% block content %}
  <!-- Page content (same as before, just the <main> content) -->
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/pages/player.js') }}?v={{ app_version }}" defer></script>
{% endblock %}
```

**Why**: `base.html` now loads all foundation CSS/JS, so pages only need to load their specific files.

---

#### Step 2: Extract Embedded `<style>` Blocks

**If page has `<style>` tags in the `<head>`**:

```html
<!-- BEFORE (in template <head>) -->
<style>
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .spinner-icon {
    animation: spin 1s linear infinite;
  }
  .match-history-table th {
    white-space: nowrap;
  }
</style>
```

**Move to** `static/css/pages/[page].css`:

```css
/* static/css/pages/player.css */

/* Spinner animation for submit button */
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.spinner-icon {
  animation: spin 1s linear infinite;
}

/* Match history table styles */
.match-history-table th {
  white-space: nowrap;
}

.match-history-table td {
  white-space: nowrap;
}
```

---

#### Step 3: Extract Inline Styles

**Pattern 1: Static Inline Styles → CSS Classes**

```html
<!-- BEFORE -->
<div style="display: flex; align-items: center; gap: 1rem">
  <h2>Player Name</h2>
</div>
```

```html
<!-- AFTER (template) -->
<div class="player-header">
  <h2>Player Name</h2>
</div>
```

```css
/* AFTER (static/css/pages/player.css) */
.player-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}
```

**Pattern 2: Visibility Toggles → Utility Classes**

```html
<!-- BEFORE -->
<div id="stat-play-card" style="display: none;">
```

```html
<!-- AFTER -->
<div id="stat-play-card" class="hidden">
  <!-- utility class from utilities/visibility.css -->
</div>
```

**Pattern 3: Dynamic Styles → CSS Custom Properties**

```html
<!-- BEFORE (dynamic color from backend) -->
<div style="background-color: {{ player_color }};">
```

```html
<!-- AFTER (template) -->
<div class="player-badge" style="--player-color: {{ player_color }};">
```

```css
/* AFTER (CSS) */
.player-badge {
  background-color: var(--player-color);
  padding: 0.5rem 1rem;
  border-radius: 4px;
}
```

**Pattern 4: Common Styles → Utilities**

If a style appears in 3+ places, make it a utility class in `utilities/` instead of page-specific:

```css
/* utilities/layout.css (if used across multiple pages) */
.flex-center {
  display: flex;
  align-items: center;
  gap: 1rem;
}
```

---

#### Step 4: Extract Inline JavaScript

**Pattern 1: Inline onclick → Event Delegation**

```html
<!-- BEFORE -->
<button onclick="removePlayer()">Remove Player</button>
```

```html
<!-- AFTER (template) -->
<button data-action="remove-player">Remove Player</button>
```

```javascript
// AFTER (static/js/pages/player.js)
document.addEventListener('DOMContentLoaded', () => {
  // Event delegation for all buttons
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action="remove-player"]');
    if (!btn) return;

    removePlayer();
  });
});

function removePlayer() {
  // Function logic here
}
```

**Pattern 2: Inline onchange → Event Delegation**

```html
<!-- BEFORE -->
<select onchange="filterMatches(this.value)">
  <option value="all">All Matches</option>
</select>
```

```html
<!-- AFTER -->
<select data-action="filter-matches">
  <option value="all">All Matches</option>
</select>
```

```javascript
// AFTER (JS)
document.addEventListener('change', (e) => {
  const select = e.target.closest('[data-action="filter-matches"]');
  if (!select) return;

  filterMatches(select.value);
});
```

---

#### Step 5: Validation Checklist (Per Page)

After refactoring each page, verify:

```bash
# 1. Zero inline styles (except truly dynamic ones)
grep 'style=' web-app/templates/pages/[page].html | wc -l
# Expected: 0 or very few (only dynamic styles like colors from DB)

# 2. Zero inline JavaScript handlers
grep -E 'on(click|change|load)=' web-app/templates/pages/[page].html | wc -l
# Expected: 0

# 3. No embedded <style> tags
grep '<style>' web-app/templates/pages/[page].html
# Expected: no output

# 4. Page extends base.html
head -1 web-app/templates/pages/[page].html
# Expected: {% extends "base.html" %}

# 5. CSS file exists and is loaded
ls static/css/pages/[page].css
grep "css/pages/[page].css" templates/pages/[page].html
# Expected: both exist

# 6. Visual test - open page in browser
# Check: page looks the same as before
# Check: no console errors
# Check: all interactive features work
```

---

## Example: Complete Refactoring of elo.html

### Before Refactoring

```html
<!-- templates/pages/elo.html (BEFORE) -->
<!doctype html>
<html>
<head>
  <title>ELO Leaderboard</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/global.css') }}">
  <style>
    .leaderboard-table {
      width: 100%;
      border-collapse: collapse;
    }
  </style>
</head>
<body>
  <div style="padding: 2rem; max-width: 1200px; margin: 0 auto;">
    <h1 style="color: var(--color-primary); margin-bottom: 1.5rem;">ELO Leaderboard</h1>

    <select onchange="filterByServer(this.value)" style="margin-bottom: 1rem;">
      <option value="all">All Servers</option>
      <option value="global">Global Only</option>
    </select>

    <table class="leaderboard-table" style="margin-top: 2rem;">
      <!-- table content -->
    </table>
  </div>
</body>
</html>
```

### After Refactoring

**Template** (`templates/pages/elo.html`):

```html
{% extends "base.html" %}

{% block title %}ELO Leaderboard - Sorcerers Summit{% endblock %}

{% block styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/elo.css') }}?v={{ app_version }}">
{% endblock %}

{% block content %}
  <div class="elo-container">
    <h1 class="elo-title">ELO Leaderboard</h1>

    <select data-action="filter-server" class="server-filter">
      <option value="all">All Servers</option>
      <option value="global">Global Only</option>
    </select>

    <table class="leaderboard-table">
      <!-- table content -->
    </table>
  </div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/pages/elo.js') }}?v={{ app_version }}" defer></script>
{% endblock %}
```

**CSS** (`static/css/pages/elo.css`):

```css
/*
 * Page: ELO Leaderboard
 * Template: templates/pages/elo.html
 * Description: Styles for the ELO ranking leaderboard page
 */

.elo-container {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.elo-title {
  color: var(--color-primary);
  margin-bottom: 1.5rem;
}

.server-filter {
  margin-bottom: 1rem;
  padding: 0.5rem;
  border-radius: var(--border-radius-md);
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}

.leaderboard-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 2rem;
}

.leaderboard-table th,
.leaderboard-table td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.leaderboard-table th {
  background: var(--color-surface);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
}

.leaderboard-table tr:hover {
  background: var(--color-surface-hover);
}
```

**JavaScript** (`static/js/pages/elo.js`):

```javascript
/**
 * Page: ELO Leaderboard
 * Template: templates/pages/elo.html
 * Description: Handles server filtering and table sorting
 */

document.addEventListener('DOMContentLoaded', () => {
  initializeServerFilter();
});

/**
 * Initialize server filter dropdown
 */
function initializeServerFilter() {
  document.addEventListener('change', (e) => {
    const select = e.target.closest('[data-action="filter-server"]');
    if (!select) return;

    filterByServer(select.value);
  });
}

/**
 * Filter leaderboard by server
 * @param {string} serverType - 'all' or 'global'
 */
function filterByServer(serverType) {
  console.log(`Filtering by server: ${serverType}`);
  // Filter logic here - update table rows based on server type
}
```

---

## Priority Order for Refactoring

Based on the audit, refactor in this order (highest impact first):

### High Priority (35-20 inline styles)
1. ✅ **player.html** (35 styles) - Start here
2. **elo.html** (25 styles) - Core feature
3. **index.html** (20 styles) - Landing page
4. **avatars.html** (20 styles) - Popular page

### Medium Priority (18-7 inline styles)
5. **metagame.html** (18)
6. **live_popular_cards.html** (9)
7. **elements.html** (9)
8. **admin_audit_log.html** (7)

### Low Priority (≤6 inline styles)
9-25. All remaining pages (can be done in parallel)

---

## Common Patterns Reference

### Flexbox Layouts

```css
/* Instead of inline: style="display: flex; align-items: center; gap: 1rem" */
.flex-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.flex-col {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.flex-between {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
```

### Card/Container Patterns

```css
/* Instead of inline: style="padding: 1.5rem; background: rgba(255,255,255,0.05);" */
.card {
  padding: var(--spacing-lg);
  background: var(--color-surface);
  border-radius: var(--border-radius-md);
}

.card-hover {
  padding: var(--spacing-lg);
  background: var(--color-surface);
  border-radius: var(--border-radius-md);
  transition: background-color var(--transition-fast);
}

.card-hover:hover {
  background: var(--color-surface-hover);
}
```

### Visibility Toggles

```css
/* Instead of inline: style="display: none" */
.hidden { display: none; }
.visible { display: block; }

/* Use JavaScript to toggle classes instead of inline styles */
// element.classList.add('hidden');
// element.classList.remove('hidden');
```

---

## Success Metrics

Track progress using:

```bash
# Overall inline styles remaining
grep -r 'style=' web-app/templates/pages/ --include="*.html" | wc -l
# Target: 0 (or only approved dynamic styles)

# Overall inline JS remaining
grep -rE 'on(click|change|load)=' web-app/templates/pages/ --include="*.html" | wc -l
# Target: 0

# Pages converted to base.html
grep -l "extends \"base.html\"" web-app/templates/pages/*.html | wc -l
# Target: 25 (all pages)

# Pages with matching CSS files
for f in web-app/templates/pages/*.html; do
  name=$(basename "$f" .html)
  [ -f "web-app/static/css/pages/${name}.css" ] && echo "✅ $name" || echo "❌ $name"
done
```

---

## Tips & Best Practices

1. **One page at a time**: Complete each page fully before moving to the next
2. **Screenshot before/after**: Visual regression is critical
3. **Test interactivity**: Click all buttons, test all filters/forms
4. **Commit per page**: `git commit -m "Refactor elo.html: extract inline styles/JS"`
5. **Use CSS variables**: Reference `base/variables.css` for colors, spacing, etc.
6. **Consistent naming**: `.page-section`, `.page-title`, `.page-card` patterns
7. **Comment your CSS**: Add header comments to each CSS file explaining its purpose

---

## Next Steps

1. **Start with player.html** (highest impact, 35 inline styles)
2. **Follow this guide step-by-step**
3. **Commit after each page is complete**
4. **Run validation after each page**
5. **Continue with elo.html, then index.html**

Good luck! The foundation is solid - now it's just systematic, page-by-page refactoring.
