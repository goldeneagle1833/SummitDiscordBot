# Research: Web App Structure Modernization

**Feature**: Web App Structure Modernization
**Date**: 2026-03-08
**Phase**: Phase 0 - Technical Research

## Research Questions

This document addresses the key technical decisions and patterns needed to successfully refactor the web app's frontend structure.

---

## 1. Inline Style Extraction Strategy

### Decision: Progressive Page-by-Page Extraction with CSS Class Creation

**Context**: 181+ inline `style` attributes across 25 page templates need to be moved to external CSS files.

**Approach**:

1. **Audit Phase**: Create inventory of all inline styles grouped by:
   - Unique styles (appear once) → page-specific CSS
   - Repeated styles (appear 3+ times) → utility classes or component CSS
   - Dynamic styles (use Jinja2 variables) → CSS custom properties

2. **Extraction Pattern**:
   ```html
   <!-- BEFORE -->
   <div style="padding: 1rem; background: rgba(255,255,255,0.05);">

   <!-- AFTER -->
   <div class="card-container">
   ```

   ```css
   /* static/css/pages/avatars.css */
   .card-container {
       padding: 1rem;
       background: rgba(255, 255, 255, 0.05);
   }
   ```

3. **Migration Order** (prioritized by impact):
   - **Phase 1**: Large, complex pages (avatars.html - 38KB, highest inline count)
   - **Phase 2**: Medium pages (elo.html, card.html, elements.html)
   - **Phase 3**: Simple pages (about.html, help.html, error pages)

4. **Validation**: After each page extraction:
   - Visual comparison (screenshot before/after)
   - Manual click-through testing
   - Verify zero `style=` attributes with grep

**Rationale**:
- Progressive approach reduces risk of visual regressions
- Starting with largest pages delivers biggest impact first
- Class-based CSS is more maintainable than inline styles
- Repeated styles become reusable utilities

**Alternatives Considered**:
- **Automated extraction tools** (CSS extractor scripts): Rejected because tools can't intelligently group related styles or identify duplicates
- **Extract all at once**: Rejected due to high risk of introducing bugs across entire site simultaneously
- **Keep inline styles, just organize templates**: Rejected because doesn't solve core maintainability problem

---

## 2. Inline JavaScript Handler Extraction

### Decision: Event Delegation with Module Pattern

**Context**: 15+ inline event handlers (`onclick`, `onchange`, `oninput`) need to be moved to external JavaScript files.

**Approach**:

1. **Event Delegation Pattern**:
   ```html
   <!-- BEFORE -->
   <button onclick="handleFilter('wins')">Filter by Wins</button>

   <!-- AFTER -->
   <button data-action="filter" data-filter-type="wins">Filter by Wins</button>
   ```

   ```javascript
   // static/js/pages/avatars.js
   document.addEventListener('DOMContentLoaded', () => {
       // Event delegation on parent container
       document.addEventListener('click', (e) => {
           const target = e.target.closest('[data-action="filter"]');
           if (!target) return;

           const filterType = target.dataset.filterType;
           handleFilter(filterType);
       });
   });

   function handleFilter(type) {
       // Filter logic here
   }
   ```

2. **Module Organization**:
   - Each page gets its own JS file: `static/js/pages/[page-name].js`
   - Components get: `static/js/components/[component-name].js`
   - Shared utilities: `static/js/utils/[utility-name].js`

3. **Loading Strategy**:
   ```html
   <!-- In base.html -->
   {% block scripts %}
   <!-- Page-specific scripts loaded here -->
   {% endblock %}

   <!-- In avatars.html -->
   {% block scripts %}
   <script src="{{ url_for('static', filename='js/pages/avatars.js') }}?v={{ app_version }}" defer></script>
   {% endblock %}
   ```

4. **DOM-Ready Initialization**:
   - All page scripts wrap logic in `DOMContentLoaded` event
   - Use `defer` attribute to ensure DOM is ready
   - No inline `onload` handlers

**Rationale**:
- Event delegation reduces memory footprint (one listener vs. many)
- `data-*` attributes provide semantic HTML without JavaScript strings
- Module pattern keeps JavaScript organized and testable
- Defer loading prevents blocking page render

**Alternatives Considered**:
- **jQuery-based approach**: Rejected because no jQuery in current stack, adds unnecessary dependency
- **Keep global functions, just externalize**: Rejected because creates global namespace pollution
- **Web Components**: Rejected as too complex for simple refactoring, requires build process

---

## 3. File Naming and Organization Conventions

### Decision: Mirror Template Structure in Static Assets

**Context**: Need clear, predictable mapping between templates and their CSS/JS files.

**Convention**:

```text
templates/pages/avatars.html
    ↓ maps to ↓
static/css/pages/avatars.css
static/js/pages/avatars.js

templates/components/navbar.html
    ↓ maps to ↓
static/css/components/navbar.css
static/js/components/navbar.js
```

**Directory Structure**:

```text
static/
├── css/
│   ├── base/                    # NEW: Global foundation styles
│   │   ├── reset.css
│   │   ├── variables.css        # CSS custom properties
│   │   └── typography.css
│   ├── components/              # EXISTING: Component styles
│   │   ├── avatar-grid.css
│   │   ├── navbar.css
│   │   └── ...
│   ├── pages/                   # EXISTING (expand): Page-specific styles
│   │   ├── avatars.css          # NEW
│   │   ├── elo.css              # NEW
│   │   └── ...
│   ├── utilities/               # NEW: Utility classes
│   │   ├── layout.css           # Flex, grid utilities
│   │   ├── spacing.css          # Margin, padding
│   │   └── colors.css           # Background, text colors
│   └── vendor/                  # NEW: Third-party CSS
│       └── tailwind.output.css  # MOVED from root
│
├── js/
│   ├── core/                    # NEW: Core JavaScript
│   │   └── main.js              # MOVED from root
│   ├── components/              # EXISTING: Component scripts
│   │   ├── navbar.js
│   │   ├── deck-viewer.js
│   │   └── ...
│   ├── pages/                   # NEW: Page-specific scripts
│   │   ├── avatars.js           # NEW
│   │   ├── elo.js               # NEW
│   │   └── ...
│   └── utils/                   # NEW: Shared utilities
│       ├── api.js               # API call helpers
│       └── dom.js               # DOM manipulation helpers
```

**Naming Rules**:
1. **Kebab-case** for all filenames: `avatar-grid.css`, `deck-viewer.js`
2. **Match template name exactly**: `avatars.html` → `avatars.css` + `avatars.js`
3. **Descriptive component names**: `navbar.js` not `nav.js`, `leaderboard.css` not `lb.css`
4. **No generic names**: Avoid `common.css`, `helpers.js`, `misc.css` (be specific about purpose)

**Loading Order** (in base.html):

```html
<!-- CSS Load Order -->
<link rel="stylesheet" href=".../vendor/tailwind.output.css">  <!-- 1. Vendor -->
<link rel="stylesheet" href=".../base/reset.css">              <!-- 2. Base -->
<link rel="stylesheet" href=".../base/variables.css">
<link rel="stylesheet" href=".../utilities/layout.css">        <!-- 3. Utilities -->
<link rel="stylesheet" href=".../components/navbar.css">       <!-- 4. Components -->
{% block styles %}{% endblock %}                                <!-- 5. Page-specific -->

<!-- JS Load Order -->
<script src=".../core/main.js" defer></script>                 <!-- 1. Core -->
<script src=".../components/navbar.js" defer></script>         <!-- 2. Components -->
{% block scripts %}{% endblock %}                               <!-- 3. Page-specific -->
```

**Rationale**:
- Mirroring template structure makes files easy to find (mental model)
- Clear categories (base/components/pages/utilities) organize by scope
- Consistent naming prevents confusion and naming conflicts
- Load order ensures dependencies are available when needed

**Alternatives Considered**:
- **Flat structure** (all CSS in one directory): Rejected because doesn't scale, hard to find files
- **Feature-based organization** (all avatar files together): Rejected because breaks template/asset separation
- **Alphabetical organization only**: Rejected because doesn't communicate file purpose/scope

---

## 4. Dynamic Styles from Jinja2 Variables

### Decision: CSS Custom Properties + Data Attributes

**Context**: Some styles are generated dynamically from Python/Jinja2 variables (e.g., chart colors, user preferences, avatar images).

**Pattern 1: CSS Custom Properties for Colors/Sizes**:

```html
<!-- BEFORE -->
<div style="background-color: {{ avatar_color }};">

<!-- AFTER -->
<div class="avatar-header" style="--avatar-color: {{ avatar_color }};">
```

```css
/* static/css/pages/avatar.css */
.avatar-header {
    background-color: var(--avatar-color);
    /* Other static styles */
    padding: 1rem;
    border-radius: 8px;
}
```

**Pattern 2: Data Attributes for JavaScript Access**:

```html
<!-- BEFORE -->
<canvas id="chart" onload="drawChart({{ data_json|safe }})">

<!-- AFTER -->
<canvas id="chart" data-chart-data="{{ data_json|tojson }}">
```

```javascript
// static/js/pages/elo.js
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('chart');
    const data = JSON.parse(canvas.dataset.chartData);
    drawChart(data);
});
```

**Pattern 3: Limited Inline for Truly Dynamic Styles**:

```html
<!-- ONLY when no alternative exists (rare) -->
<div class="avatar-bg" style="background-image: url('{{ avatar_image_url }}');">
```

**Acceptance Criteria for Inline Styles**:
- ✅ Allowed: Dynamic URLs (image paths, avatar URLs from database)
- ✅ Allowed: User-specific colors/themes from database
- ❌ Not allowed: Static positioning, sizing, spacing (use CSS classes)
- ❌ Not allowed: Repeated patterns (extract to utilities)

**Rationale**:
- CSS custom properties keep styling logic in CSS files while allowing dynamic values
- Data attributes separate data from presentation
- Minimal inline styles for truly dynamic content (1-2 per page acceptable)
- Clear rules prevent inline style creep

**Alternatives Considered**:
- **Generate CSS files dynamically**: Rejected due to caching issues and complexity
- **Use JavaScript to set all styles**: Rejected because causes flash of unstyled content
- **Inline styles for all dynamic content**: Rejected because violates separation of concerns

---

## 5. Migration and Testing Strategy

### Decision: Incremental Page Migration with Visual Regression Testing

**Migration Workflow**:

1. **Pre-Migration** (per page):
   - Take screenshot of current page state
   - Document all interactive features (buttons, filters, forms)
   - Identify all inline styles and handlers

2. **Extraction** (per page):
   - Create `static/css/pages/[page].css`
   - Create `static/js/pages/[page].js` (if needed)
   - Extract styles → classes in CSS file
   - Extract handlers → event listeners in JS file
   - Update template to load new assets in `{% block styles/scripts %}`

3. **Validation** (per page):
   - Verify zero `grep 'style=' templates/pages/[page].html`
   - Verify zero `grep 'onclick=' templates/pages/[page].html`
   - Take post-migration screenshot
   - Visual comparison (pixel-diff or manual review)
   - Manual testing of all interactive features
   - Check browser console for JavaScript errors

4. **Commit Strategy**:
   - One commit per page: "Refactor [page].html: extract inline styles/scripts"
   - Commit message includes before/after metrics
   - Each commit is independently reviewable and revertable

**Testing Checklist Template**:

```markdown
## Page: avatars.html

### Pre-Migration
- [x] Screenshot captured: `docs/refactor/before-avatars.png`
- [x] Inline styles counted: 89
- [x] Inline handlers counted: 6
- [x] Interactive features documented: filter dropdown, sort selector, popularity chart

### Extraction
- [x] Created static/css/pages/avatars.css
- [x] Created static/js/pages/avatars.js
- [x] All styles extracted to CSS classes
- [x] All handlers extracted to event listeners
- [x] Template updated to load new assets

### Post-Migration Validation
- [x] `grep 'style=' templates/pages/avatars.html` → 0 results
- [x] `grep 'onclick=' templates/pages/avatars.html` → 0 results
- [x] Screenshot captured: `docs/refactor/after-avatars.png`
- [x] Visual comparison: ✅ Identical
- [x] Filter dropdown: ✅ Works
- [x] Sort selector: ✅ Works
- [x] Popularity chart: ✅ Renders
- [x] Browser console: ✅ No errors
```

**Prioritization** (based on complexity and impact):

| Priority | Page | Inline Styles | Inline JS | Complexity | Impact |
|----------|------|---------------|-----------|------------|--------|
| P1 | avatars.html | ~90 | 6 | High | High (most complex page) |
| P1 | elo.html | ~40 | 3 | Medium | High (core feature) |
| P2 | elements.html | ~30 | 2 | Medium | Medium |
| P2 | card.html | ~25 | 1 | Low | Medium |
| P3 | about.html | ~5 | 0 | Low | Low |

**Rollback Plan**:
- Each page refactor is in its own commit
- Revert specific page if regression found: `git revert <commit-hash>`
- No cross-page dependencies (each page migration is independent)

**Rationale**:
- Incremental approach limits blast radius of any mistakes
- Visual regression testing catches layout/styling bugs
- Per-page commits enable selective rollback
- Clear testing checklist ensures nothing is missed

**Alternatives Considered**:
- **Automated visual testing tools** (Percy, Chromatic): Rejected due to setup cost and no existing CI/CD for frontend
- **Unit tests for CSS/JS**: Rejected as overkill for refactoring (integration tests more valuable)
- **Big bang migration**: Rejected due to high risk of widespread regressions

---

## 6. Global Styles Consolidation

### Decision: Merge and Categorize into Base/Utilities Structure

**Context**: Global styles currently scattered across:
- `global.css` (4.7KB)
- `style.css` (25KB - unclear purpose)
- `utilities.css` (4KB)

**Consolidation Strategy**:

1. **Audit Current Files**:
   - Read each file and categorize rules by purpose
   - Identify duplicates (same selector or same rule)
   - Find unused styles (grep for class names in templates)

2. **New Structure**:

```text
static/css/base/
├── reset.css           # Browser resets (extract from global.css)
├── variables.css       # CSS custom properties (NEW)
├── typography.css      # Font styles, headings (extract from global.css)
└── layout.css          # Container widths, page structure (extract from global.css)

static/css/utilities/
├── spacing.css         # Margin/padding utilities (from utilities.css)
├── colors.css          # Background/text color utilities (NEW)
├── flexbox.css         # Flex utilities (NEW)
└── visibility.css      # Show/hide utilities (NEW)
```

3. **Migration of style.css**:
   - Audit all rules in `style.css`
   - Move page-specific styles to `static/css/pages/[page].css`
   - Move component styles to `static/css/components/[component].css`
   - Move utilities to `static/css/utilities/[category].css`
   - **Delete style.css when empty** (goal: eliminate this file entirely)

4. **Tailwind Coexistence**:
   - Keep Tailwind for utility-first approach (margins, padding, flex)
   - Custom utilities in `utilities/` for project-specific patterns Tailwind doesn't cover
   - No duplication: if Tailwind has it, don't create custom utility

**Before/After Comparison**:

```text
BEFORE:
static/css/
├── global.css          (4.7KB - mix of resets, typography, layout)
├── style.css           (25KB - catch-all, unclear purpose)
├── utilities.css       (4KB - spacing/visibility utilities)
└── tailwind.output.css (12KB)
TOTAL: 46KB CSS, unclear organization

AFTER:
static/css/
├── base/
│   ├── reset.css       (~1KB)
│   ├── variables.css   (~1KB - CSS custom properties)
│   ├── typography.css  (~2KB)
│   └── layout.css      (~1KB)
├── utilities/
│   ├── spacing.css     (~2KB - if needed beyond Tailwind)
│   ├── colors.css      (~1KB - project-specific colors)
│   └── visibility.css  (~0.5KB)
├── components/         (existing ~10 files)
├── pages/              (new ~25 files from extraction)
└── vendor/
    └── tailwind.output.css (12KB)
TOTAL: Similar size, but ORGANIZED and purposeful
```

**Rationale**:
- Clear categorization makes styles easy to find and maintain
- Eliminates duplicate/conflicting rules
- Removes unused styles (reduces CSS size)
- Coexists with Tailwind without duplication

**Alternatives Considered**:
- **Keep existing structure, just add pages/**: Rejected because doesn't solve global.css/style.css confusion
- **Single app.css file**: Rejected because doesn't scale, hard to navigate
- **Remove Tailwind entirely**: Rejected because Tailwind provides good utility baseline

---

## 7. Documentation and Onboarding

### Decision: Comprehensive Developer Guide + Inline Comments

**Documentation Artifacts**:

1. **Developer Guide** (`web-app/docs/frontend-structure.md`):
   - Overview of folder structure
   - File naming conventions
   - How to add a new page (step-by-step)
   - How to add a new component
   - CSS/JS loading order
   - Examples of good patterns

2. **Inline Comments** (in base.html):
   ```html
   <!-- CSS Load Order: vendor → base → utilities → components → page-specific -->
   <link rel="stylesheet" href="{{ url_for('static', filename='css/vendor/tailwind.output.css') }}?v={{ app_version }}">
   <link rel="stylesheet" href="{{ url_for('static', filename='css/base/variables.css') }}?v={{ app_version }}">
   <!-- Component-specific styles loaded here via includes -->

   <!-- Page-specific CSS loaded in child templates via {% block styles %} -->
   {% block styles %}{% endblock %}
   ```

3. **Code Review Checklist** (`.github/PULL_REQUEST_TEMPLATE.md`):
   ```markdown
   ## Frontend Checklist (if applicable)
   - [ ] No inline `style` attributes added
   - [ ] No inline `onclick`/event handlers added
   - [ ] CSS files follow naming convention (`pages/` or `components/`)
   - [ ] JS files follow naming convention (`pages/` or `components/`)
   - [ ] Assets loaded in appropriate `{% block styles/scripts %}`
   ```

4. **New Page Template** (`web-app/docs/templates/new-page-template.html`):
   ```html
   {% extends "base.html" %}

   {% block title %}[Page Title]{% endblock %}

   {% block styles %}
   <link rel="stylesheet" href="{{ url_for('static', filename='css/pages/[page-name].css') }}?v={{ app_version }}">
   {% endblock %}

   {% block content %}
   <!-- Page content here -->
   {% endblock %}

   {% block scripts %}
   <script src="{{ url_for('static', filename='js/pages/[page-name].js') }}?v={{ app_version }}" defer></script>
   {% endblock %}
   ```

**Onboarding Workflow**:
1. New developer reads `frontend-structure.md`
2. Reviews example page (e.g., `pages/about.html` - simple, clean)
3. Uses `new-page-template.html` to create new page
4. Follows PR checklist to ensure compliance

**Rationale**:
- Documentation prevents knowledge loss and reverting to old patterns
- Templates make it easy to do the right thing
- PR checklist enforces standards without manual review burden

---

## Research Summary

All technical decisions for the web app structure modernization have been documented:

1. ✅ **Inline Style Extraction**: Progressive page-by-page with CSS class creation
2. ✅ **JavaScript Handler Extraction**: Event delegation with module pattern
3. ✅ **File Naming/Organization**: Mirror template structure, clear categories
4. ✅ **Dynamic Styles**: CSS custom properties + data attributes
5. ✅ **Migration Strategy**: Incremental with visual regression testing
6. ✅ **Global Styles**: Consolidate into base/utilities structure
7. ✅ **Documentation**: Developer guide + templates + PR checklist

**No Remaining Clarifications** - All "NEEDS CLARIFICATION" items from Technical Context have been resolved through research.

**Ready for Phase 1**: Design artifacts (data-model.md, contracts/, quickstart.md)
