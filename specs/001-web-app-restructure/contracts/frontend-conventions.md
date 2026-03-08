# Frontend Structure Contract

**Version**: 1.0.0
**Effective Date**: 2026-03-08
**Scope**: All Flask templates and static assets in `web-app/`

## Purpose

This contract defines the mandatory conventions for organizing HTML templates, CSS stylesheets, and JavaScript files in the Summit Discord Bot web application. All developers MUST follow these conventions when adding or modifying frontend code.

---

## Contract Guarantees

When you follow these conventions, you are guaranteed:

1. ✅ **Predictable File Locations**: You can find any page's styles/scripts in under 30 seconds
2. ✅ **No Style Conflicts**: CSS scoping prevents unintended style leakage
3. ✅ **Fast Code Reviews**: Reviewers can quickly locate and verify changes
4. ✅ **Easy Onboarding**: New developers can add pages without mentoring

---

## Mandatory Rules

### Rule 1: Zero Inline Styles

**Requirement**: Templates MUST NOT contain inline `style` attributes.

**Rationale**: Inline styles violate separation of concerns, prevent CSS reusability, and make global design changes difficult.

**Enforcement**:
```bash
# This MUST return 0 results:
grep -r 'style=' web-app/templates/ --include="*.html"
```

**Exceptions**:
- ✅ **Allowed**: Dynamic styles from server variables when no alternative exists
  ```html
  <!-- ACCEPTABLE (only if truly dynamic) -->
  <div style="background-image: url('{{ user.avatar_url }}');">
  ```

- ❌ **Not Allowed**: Static positioning, sizing, spacing, colors
  ```html
  <!-- REJECTED -->
  <div style="padding: 1rem; color: #fff;">
  ```

**Correct Approach**:
```html
<!-- Template -->
<div class="user-avatar" style="--avatar-url: url('{{ user.avatar_url }}');">

<!-- CSS -->
.user-avatar {
    background-image: var(--avatar-url);
    width: 48px;
    height: 48px;
    border-radius: 50%;
}
```

---

### Rule 2: Zero Inline JavaScript

**Requirement**: Templates MUST NOT contain inline event handlers (`onclick`, `onchange`, `oninput`, etc.).

**Rationale**: Inline JavaScript violates Content Security Policy best practices, makes code untestable, and prevents bundling/minification.

**Enforcement**:
```bash
# This MUST return 0 results:
grep -rE 'on(click|change|load|input|submit|focus|blur)=' web-app/templates/ --include="*.html"
```

**Correct Approach**:
```html
<!-- BEFORE (REJECTED) -->
<button onclick="filterBy('wins')">Filter by Wins</button>

<!-- AFTER (CORRECT) -->
<button data-action="filter" data-filter-type="wins">Filter by Wins</button>
```

```javascript
// static/js/pages/avatars.js
document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action="filter"]');
        if (!btn) return;

        const filterType = btn.dataset.filterType;
        filterBy(filterType);
    });
});
```

---

### Rule 3: File Naming Convention

**Requirement**: Template names MUST exactly match their corresponding CSS and JavaScript filenames.

**Naming Rules**:
- Use **kebab-case** for all filenames: `avatar-grid.css`, `deck-viewer.js`
- Template name determines asset names:
  ```
  templates/pages/avatars.html
      ↓
  static/css/pages/avatars.css
  static/js/pages/avatars.js
  ```

**Enforcement**:
```bash
# Verify naming consistency
for template in web-app/templates/pages/*.html; do
    name=$(basename "$template" .html)
    css="web-app/static/css/pages/${name}.css"
    [ -f "$css" ] || echo "Missing CSS for $name"
done
```

**Examples**:

| Template | CSS File | JS File |
|----------|----------|---------|
| `templates/pages/avatars.html` | `static/css/pages/avatars.css` | `static/js/pages/avatars.js` |
| `templates/pages/elo.html` | `static/css/pages/elo.css` | `static/js/pages/elo.js` |
| `templates/components/navbar.html` | `static/css/components/navbar.css` | `static/js/components/navbar.js` |

---

### Rule 4: Directory Structure

**Requirement**: CSS and JavaScript files MUST be organized into the following categories.

**CSS Categories**:

```
static/css/
├── base/              # Global foundation styles (reset, typography, variables)
├── components/        # Reusable component styles (navbar, modals, cards)
├── pages/             # Page-specific styles (avatars.css, elo.css)
├── utilities/         # Utility classes (layout, spacing, colors)
└── vendor/            # Third-party CSS (tailwind, etc.)
```

**JavaScript Categories**:

```
static/js/
├── core/              # Global scripts (main.js)
├── components/        # Component scripts (navbar.js, deck-viewer.js)
├── pages/             # Page-specific scripts (avatars.js, elo.js)
└── utils/             # Shared utilities (api.js, dom.js)
```

**Enforcement**:
- All new CSS files MUST be placed in one of: `base/`, `components/`, `pages/`, `utilities/`, `vendor/`
- All new JS files MUST be placed in one of: `core/`, `components/`, `pages/`, `utils/`

---

### Rule 5: Asset Loading

**Requirement**: Page-specific and component-specific assets MUST be loaded using Jinja2 blocks, not in `base.html`.

**Template Structure**:

```html
{% extends "base.html" %}

{% block title %}Page Title{% endblock %}

<!-- Load page-specific CSS -->
{% block styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/avatars.css') }}?v={{ app_version }}">
{% endblock %}

{% block content %}
<!-- Page content here -->
{% endblock %}

<!-- Load page-specific JS -->
{% block scripts %}
<script src="{{ url_for('static', filename='js/pages/avatars.js') }}?v={{ app_version }}" defer></script>
{% endblock %}
```

**Load Order** (base.html handles this):
1. **Vendor CSS** (Tailwind) - loaded globally
2. **Base CSS** (reset, variables, typography) - loaded globally
3. **Utilities CSS** (layout, spacing, colors) - loaded globally
4. **Component CSS** (navbar, footer) - loaded globally if used site-wide
5. **Page-specific CSS** - loaded via `{% block styles %}`
6. **Core JS** (main.js) - loaded globally
7. **Component JS** (navbar.js) - loaded globally if used site-wide
8. **Page-specific JS** - loaded via `{% block scripts %}`

**Cache Busting**:
- All asset URLs MUST include `?v={{ app_version }}` query parameter
- This ensures browsers fetch updated assets when version changes

---

## Developer Workflows

### Workflow 1: Adding a New Page

**Steps**:

1. **Create Template**:
   ```bash
   # Create page template
   touch web-app/templates/pages/my-page.html
   ```

2. **Create CSS File**:
   ```bash
   # Create matching CSS file
   touch web-app/static/css/pages/my-page.css
   ```

3. **Create JS File** (if needed):
   ```bash
   # Create matching JS file
   touch web-app/static/js/pages/my-page.js
   ```

4. **Use Template Boilerplate**:
   ```html
   {% extends "base.html" %}

   {% block title %}My Page{% endblock %}

   {% block styles %}
   <link rel="stylesheet" href="{{ url_for('static', filename='css/pages/my-page.css') }}?v={{ app_version }}">
   {% endblock %}

   {% block content %}
   <!-- Page content -->
   {% endblock %}

   {% block scripts %}
   <script src="{{ url_for('static', filename='js/pages/my-page.js') }}?v={{ app_version }}" defer></script>
   {% endblock %}
   ```

5. **Verify Compliance**:
   ```bash
   # Check no inline styles
   grep 'style=' web-app/templates/pages/my-page.html
   # Expected: 0 results

   # Check no inline JS
   grep -E 'on(click|change)=' web-app/templates/pages/my-page.html
   # Expected: 0 results
   ```

---

### Workflow 2: Adding a New Component

**Steps**:

1. **Create Component Template**:
   ```bash
   touch web-app/templates/components/my-component.html
   ```

2. **Create Component CSS**:
   ```bash
   touch web-app/static/css/components/my-component.css
   ```

3. **Create Component JS** (if needed):
   ```bash
   touch web-app/static/js/components/my-component.js
   ```

4. **Include in base.html** (if used site-wide):
   ```html
   <!-- base.html -->
   <link rel="stylesheet" href="{{ url_for('static', filename='css/components/my-component.css') }}?v={{ app_version }}">
   ```

5. **Or Include in Page** (if page-specific):
   ```html
   <!-- In page template -->
   {% include 'components/my-component.html' %}

   {% block styles %}
   {{ super() }}  <!-- Keep parent block content -->
   <link rel="stylesheet" href="{{ url_for('static', filename='css/components/my-component.css') }}?v={{ app_version }}">
   {% endblock %}
   ```

---

### Workflow 3: Refactoring Existing Page

**Steps**:

1. **Take Screenshot** (for visual comparison):
   ```bash
   # Open page in browser, take screenshot
   # Save as docs/refactor/before-{page}.png
   ```

2. **Create CSS File**:
   ```bash
   touch web-app/static/css/pages/{page}.css
   ```

3. **Extract Inline Styles**:
   - Find all `style=` attributes
   - Create CSS classes for each unique style
   - Replace inline styles with class names
   - Add CSS rules to `pages/{page}.css`

4. **Extract Inline JavaScript**:
   - Find all `onclick=`, `onchange=`, etc.
   - Create event listeners in `pages/{page}.js`
   - Replace inline handlers with `data-*` attributes
   - Implement event delegation

5. **Update Template**:
   ```html
   {% block styles %}
   <link rel="stylesheet" href="{{ url_for('static', filename='css/pages/{page}.css') }}?v={{ app_version }}">
   {% endblock %}

   {% block scripts %}
   <script src="{{ url_for('static', filename='js/pages/{page}.js') }}?v={{ app_version }}" defer></script>
   {% endblock %}
   ```

6. **Verify**:
   ```bash
   # Check zero inline styles
   grep 'style=' web-app/templates/pages/{page}.html
   # Expected: 0 results (or only truly dynamic styles)

   # Check zero inline JS
   grep -E 'onclick=' web-app/templates/pages/{page}.html
   # Expected: 0 results

   # Visual comparison
   # Open page, compare with before screenshot
   ```

---

## Code Review Checklist

All pull requests that modify frontend code MUST pass this checklist:

### CSS/Styling

- [ ] No inline `style` attributes added (except truly dynamic styles)
- [ ] New CSS file follows naming convention (matches template name)
- [ ] CSS file is in correct category (`base/`, `components/`, `pages/`, `utilities/`, `vendor/`)
- [ ] CSS loaded in appropriate block (`{% block styles %}` for page-specific)
- [ ] Asset URL includes cache-busting query param `?v={{ app_version }}`

### JavaScript

- [ ] No inline event handlers added (`onclick`, `onchange`, etc.)
- [ ] New JS file follows naming convention (matches template name)
- [ ] JS file is in correct category (`core/`, `components/`, `pages/`, `utils/`)
- [ ] Event listeners use event delegation pattern
- [ ] Code wrapped in `DOMContentLoaded` event listener
- [ ] Script tag uses `defer` attribute
- [ ] Asset URL includes cache-busting query param `?v={{ app_version }}`

### Templates

- [ ] Template extends `base.html` (for pages)
- [ ] Page-specific assets loaded in `{% block styles %}` and `{% block scripts %}`
- [ ] No global assets duplicated in page blocks
- [ ] Template filename matches CSS/JS filenames

### Testing

- [ ] Visual comparison confirms no regressions
- [ ] All interactive features tested and working
- [ ] Browser console shows no JavaScript errors

---

## Exceptions and Approvals

### Requesting an Exception

If you believe an exception to these rules is necessary, you MUST:

1. Document the reason in the PR description
2. Provide alternatives considered and why they were rejected
3. Get approval from at least one senior developer
4. Add a comment in code explaining the exception

**Example**:
```html
<!-- EXCEPTION: Dynamic background color from user preference -->
<!-- Approved by: @senior-dev on 2026-03-10 -->
<!-- Alternative rejected: CSS custom properties don't work with linear-gradient syntax in this case -->
<div style="background: linear-gradient({{ user.gradient_start }}, {{ user.gradient_end }});">
```

### Common Exception Cases

| Case | Approved? | Reasoning |
|------|-----------|-----------|
| Dynamic URLs from database (avatars, images) | ✅ Yes | No alternative for runtime URLs |
| User-specific colors/themes from DB | ✅ Yes | CSS variables not supported in all contexts |
| Static positioning/spacing | ❌ No | Use CSS classes |
| Static colors/fonts | ❌ No | Use CSS classes or Tailwind utilities |
| Inline click handlers | ❌ No | Use event delegation |

---

## Versioning

**Current Version**: 1.0.0

**Breaking Changes**: Any changes to this contract that would require updating existing code are considered breaking changes and MUST increment the major version (e.g., 1.0.0 → 2.0.0).

**Version History**:
- **1.0.0** (2026-03-08): Initial contract established during web app structure modernization

---

## Compliance Validation

### Automated Checks

Run these commands to verify compliance:

```bash
# Check for inline styles
echo "=== Checking for inline styles ==="
grep -r 'style=' web-app/templates/ --include="*.html" | wc -l
# Expected: 0 (or only approved exceptions)

# Check for inline JavaScript
echo "=== Checking for inline JavaScript ==="
grep -rE 'on(click|change|load|input|submit|focus|blur)=' web-app/templates/ --include="*.html" | wc -l
# Expected: 0

# Check file naming consistency
echo "=== Checking file naming consistency ==="
for template in web-app/templates/pages/*.html; do
    name=$(basename "$template" .html)
    css="web-app/static/css/pages/${name}.css"
    [ -f "$css" ] || echo "MISSING CSS: $name"
done
# Expected: No output (all pages have matching CSS files)
```

### Manual Checks

- Review new templates for proper use of `{% block styles %}` and `{% block scripts %}`
- Verify asset URLs include `?v={{ app_version }}`
- Confirm load order is correct (vendor → base → utilities → components → pages)

---

## Summary

This contract ensures:

1. ✅ **Separation of Concerns**: HTML, CSS, and JavaScript are in separate files
2. ✅ **Predictable Organization**: File locations follow clear, consistent patterns
3. ✅ **Easy Discovery**: Find any page's assets by name matching
4. ✅ **Maintainability**: Changes are scoped to specific files, not scattered across templates

**When in doubt, ask**: If you're unsure whether your code follows these conventions, ask in code review or check existing examples (e.g., `pages/about.html` for a simple, clean page).
