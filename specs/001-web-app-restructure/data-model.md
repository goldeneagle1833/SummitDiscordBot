# Data Model: Web App Structure Modernization

**Feature**: Web App Structure Modernization
**Date**: 2026-03-08
**Phase**: Phase 1 - Design

## Overview

This "data model" describes the entities (file types) and their relationships in the refactored frontend structure. While this isn't a traditional data model with database entities, understanding the file structure as a relational model helps ensure consistency.

---

## Entity Definitions

### 1. Template File

**Description**: HTML template file using Jinja2 syntax for server-side rendering.

**Attributes**:
- **Path**: `templates/{category}/{name}.html`
- **Category**: One of `pages`, `components`, `errors`, or root (e.g., `base.html`)
- **Name**: Kebab-case filename matching the page or component purpose
- **Has CSS**: Boolean - whether this template has corresponding CSS file
- **Has JS**: Boolean - whether this template has corresponding JavaScript file
- **Extends**: Reference to parent template (usually `base.html` for pages)
- **Includes**: List of component templates included via `{% include %}`

**Validation Rules**:
- MUST NOT contain inline `style` attributes (count = 0)
- MUST NOT contain inline event handlers like `onclick`, `onchange` (count = 0)
- MUST define `{% block styles %}` if has CSS
- MUST define `{% block scripts %}` if has JS
- Name MUST match corresponding CSS/JS filenames exactly

**Relationships**:
- `has_css_file` → CSS File (1:1, optional)
- `has_js_file` → JavaScript File (1:1, optional)
- `extends` → Template File (many:1)
- `includes` → Template File (many:many)

**Examples**:
```
templates/pages/avatars.html
    Category: pages
    Name: avatars
    Has CSS: true → static/css/pages/avatars.css
    Has JS: true → static/js/pages/avatars.js
    Extends: base.html
    Includes: components/navbar.html, components/footer.html
```

---

### 2. CSS File

**Description**: Stylesheet file containing visual presentation rules.

**Attributes**:
- **Path**: `static/css/{category}/{name}.css`
- **Category**: One of `base`, `components`, `pages`, `utilities`, `vendor`
- **Name**: Kebab-case filename
- **Scope**: One of `global`, `page-specific`, `component-specific`, `utility`
- **Size**: File size in KB
- **Load Order**: Integer priority (1=first, 5=last)

**Validation Rules**:
- Category MUST be one of: `base`, `components`, `pages`, `utilities`, `vendor`
- If Category = `pages`, Name MUST match a template in `templates/pages/`
- If Category = `components`, Name MUST match a template in `templates/components/`
- Load Order MUST respect: vendor(1) → base(2) → utilities(3) → components(4) → pages(5)

**Relationships**:
- `styles_template` → Template File (many:1)
- `loaded_by` → Template File (many:1, via base.html or {% block styles %})

**Examples**:
```
static/css/pages/avatars.css
    Category: pages
    Name: avatars
    Scope: page-specific
    Load Order: 5 (page-specific, last)
    Styles Template: templates/pages/avatars.html

static/css/base/variables.css
    Category: base
    Name: variables
    Scope: global
    Load Order: 2 (base styles, early)
    Loaded By: base.html (all pages)
```

---

### 3. JavaScript File

**Description**: Script file containing client-side behavior and interactivity.

**Attributes**:
- **Path**: `static/js/{category}/{name}.js`
- **Category**: One of `core`, `components`, `pages`, `utils`
- **Name**: Kebab-case filename
- **Scope**: One of `global`, `page-specific`, `component-specific`, `utility`
- **Load Strategy**: One of `defer`, `async`, `blocking` (default: defer)

**Validation Rules**:
- Category MUST be one of: `core`, `components`, `pages`, `utils`
- If Category = `pages`, Name MUST match a template in `templates/pages/`
- If Category = `components`, Name MUST match a template in `templates/components/`
- Load Strategy MUST be `defer` for page/component scripts (prevent blocking)
- All page/component scripts MUST wrap logic in `DOMContentLoaded` event listener

**Relationships**:
- `adds_behavior_to` → Template File (many:1)
- `depends_on` → JavaScript File (many:many, e.g., utils)

**Examples**:
```
static/js/pages/avatars.js
    Category: pages
    Name: avatars
    Scope: page-specific
    Load Strategy: defer
    Adds Behavior To: templates/pages/avatars.html
    Depends On: static/js/utils/api.js

static/js/core/main.js
    Category: core
    Name: main
    Scope: global
    Load Strategy: defer
    Adds Behavior To: base.html (all pages)
```

---

### 4. Asset Loading Directive

**Description**: Jinja2 block in template that specifies which CSS/JS files to load.

**Attributes**:
- **Template**: Reference to template file containing the directive
- **Block Type**: One of `styles` (CSS) or `scripts` (JS)
- **Assets**: List of CSS or JS file paths to load
- **Load Point**: One of `base` (global), `page` (page-specific block)

**Validation Rules**:
- Block Type `styles` MUST only load CSS files
- Block Type `scripts` MUST only load JS files
- Assets loaded in `page` block MUST NOT be loaded in `base` (avoid duplication)
- All asset paths MUST use `url_for('static', filename='...')` helper
- All asset URLs MUST include cache-busting query param `?v={{ app_version }}`

**Relationships**:
- `defined_in` → Template File (many:1)
- `loads_assets` → CSS File or JavaScript File (1:many)

**Examples**:
```
Asset Loading Directive in templates/pages/avatars.html:

{% block styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/avatars.css') }}?v={{ app_version }}">
{% endblock %}

    Template: templates/pages/avatars.html
    Block Type: styles
    Assets: [static/css/pages/avatars.css]
    Load Point: page
```

---

## Entity Relationships Diagram

```
┌─────────────────┐
│  Template File  │
│  (Jinja2 HTML)  │
└────────┬────────┘
         │
         │ extends (many:1)
         ├──────────────► Template File (base.html)
         │
         │ includes (many:many)
         ├──────────────► Template File (components)
         │
         │ has_css_file (1:1)
         ├──────────────► ┌─────────────┐
         │                 │  CSS File   │
         │                 │  (.css)     │
         │                 └─────────────┘
         │
         │ has_js_file (1:1)
         └──────────────► ┌─────────────┐
                          │ JS File     │
                          │ (.js)       │
                          └─────────────┘

┌──────────────────────┐
│ Asset Loading        │
│ Directive            │
│ ({% block %})        │
└──────┬───────────────┘
       │
       │ defined_in (many:1)
       ├─────────────► Template File
       │
       │ loads_assets (1:many)
       └─────────────► CSS File or JS File
```

---

## State Transitions

### Template File Lifecycle

```
1. [LEGACY] - Has inline styles/scripts
       ↓
   (Refactoring)
       ↓
2. [EXTRACTING] - CSS/JS files created, template being updated
       ↓
   (Validation)
       ↓
3. [CLEAN] - Zero inline styles/scripts, loads external assets
       ↓
   (Maintenance)
       ↓
4. [MAINTAINED] - New features follow conventions
```

**Acceptance Criteria for State Transitions**:

- **LEGACY → EXTRACTING**:
  - CSS file created in `static/css/{category}/`
  - JS file created (if needed) in `static/js/{category}/`
  - Inline styles/scripts identified and documented

- **EXTRACTING → CLEAN**:
  - ✅ `grep 'style=' templates/{category}/{name}.html` returns 0 results
  - ✅ `grep 'onclick=' templates/{category}/{name}.html` returns 0 results
  - ✅ Template includes `{% block styles %}` and/or `{% block scripts %}`
  - ✅ Visual comparison confirms no regressions
  - ✅ All interactive features tested and working

- **CLEAN → MAINTAINED**:
  - ✅ Code review confirms no inline styles/scripts added
  - ✅ New features follow file naming conventions
  - ✅ Documentation updated if patterns change

---

## Data Integrity Constraints

### Cross-Entity Constraints

1. **Template ↔ CSS Naming Consistency**:
   ```
   FOR EACH template IN templates/pages/:
       IF template.has_css = true:
           ASSERT EXISTS css_file WHERE:
               css_file.path = "static/css/pages/{template.name}.css"
   ```

2. **Template ↔ JS Naming Consistency**:
   ```
   FOR EACH template IN templates/pages/:
       IF template.has_js = true:
           ASSERT EXISTS js_file WHERE:
               js_file.path = "static/js/pages/{template.name}.js"
   ```

3. **Zero Inline Styles**:
   ```
   FOR EACH template IN templates/:
       ASSERT COUNT(template.inline_styles) = 0
   ```

4. **Zero Inline JavaScript**:
   ```
   FOR EACH template IN templates/:
       ASSERT COUNT(template.inline_handlers) = 0
   ```

5. **CSS Load Order**:
   ```
   FOR EACH css_file IN loaded_assets:
       ASSERT css_file.load_order IN (1, 2, 3, 4, 5)
       ASSERT vendor (1) loads before base (2)
       ASSERT base (2) loads before utilities (3)
       ASSERT utilities (3) loads before components (4)
       ASSERT components (4) loads before pages (5)
   ```

6. **No Duplicate Asset Loading**:
   ```
   FOR EACH template:
       FOR EACH asset IN template.loaded_assets:
           ASSERT asset NOT IN base.html.loaded_assets
           (page-specific assets must not be in global base.html)
   ```

---

## Validation Queries

### Query 1: Find Templates Missing CSS Files

```bash
# Find page templates without corresponding CSS files
for template in web-app/templates/pages/*.html; do
    basename="${template##*/}"
    name="${basename%.html}"
    css_file="web-app/static/css/pages/${name}.css"
    if [ ! -f "$css_file" ]; then
        echo "MISSING CSS: $template → $css_file"
    fi
done
```

### Query 2: Find Inline Styles in Templates

```bash
# Find templates with inline style attributes
grep -r 'style=' web-app/templates/ --include="*.html"
# Expected result after refactoring: 0 matches
```

### Query 3: Find Inline JavaScript Handlers

```bash
# Find templates with inline event handlers
grep -rE 'on(click|change|load|input|submit|focus|blur)=' web-app/templates/ --include="*.html"
# Expected result after refactoring: 0 matches
```

### Query 4: Verify File Naming Consistency

```bash
# Check that all page templates have matching CSS filenames
for template in web-app/templates/pages/*.html; do
    template_name=$(basename "$template" .html)
    css_name=$(basename "web-app/static/css/pages/${template_name}.css" .css)
    if [ "$template_name" != "$css_name" ]; then
        echo "NAME MISMATCH: Template '$template_name' vs CSS '$css_name'"
    fi
done
```

---

## Summary

The refactored structure treats templates, CSS files, and JavaScript files as related entities with strict naming conventions and validation rules. This "data model" ensures:

1. **Consistency**: 1:1 mapping between templates and assets (by name)
2. **Integrity**: Zero inline styles/scripts enforced via validation
3. **Discoverability**: Predictable file locations based on template category
4. **Maintainability**: Clear constraints prevent regressions

All entities follow the relationship diagram and state transitions, ensuring a clean, organized frontend architecture.
