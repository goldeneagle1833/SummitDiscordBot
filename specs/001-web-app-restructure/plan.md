# Implementation Plan: Web App Structure Modernization

**Branch**: `001-web-app-restructure` | **Date**: 2026-03-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-web-app-restructure/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

This feature eliminates inline styles (181+ instances) and inline JavaScript handlers (15+ instances) from Flask/Jinja2 templates, reorganizes CSS and JavaScript assets into a clear, predictable structure, and establishes conventions for maintaining separation of concerns. The goal is to improve developer productivity (30 seconds to locate any component's styles vs. 2-3 minutes currently), reduce code review time by 40%, and enable new developers to add pages following the structure in under 15 minutes.

## Technical Context

**Language/Version**: Python 3.11.6
**Primary Dependencies**: Flask 3.0+, Jinja2 (template engine), Gunicorn (WSGI server), Tailwind CSS (utility framework)
**Storage**: N/A (this is a frontend refactoring, backend uses SQLite but not relevant here)
**Testing**: No frontend tests currently (pytest used for backend only)
**Target Platform**: Web browsers (production deployment via Nginx + Cloudflare)
**Project Type**: Web application (Flask-based with server-side rendering)
**Performance Goals**: No changes to runtime performance (structural refactoring only)
**Constraints**:
- Must preserve existing page functionality (no behavior changes)
- Must maintain compatibility with Tailwind utility classes in HTML
- Must work with Jinja2 templating syntax
- No build process available (manual organization only)
**Scale/Scope**:
- 31 HTML templates (25 pages, 3 components, 3 other)
- 181+ inline style attributes to extract
- 15+ inline JavaScript handlers to externalize
- 16 existing CSS files (mix of component/page/global)
- 6 existing JavaScript files (mostly components)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: ✅ **SKIPPED** - No project constitution exists (`.specify/memory/constitution.md` is an empty template)

This is a refactoring task within an existing web application. No architectural principles are being violated. The refactoring improves code organization without changing functionality.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

**Current Structure** (affects this feature):

```text
web-app/
├── templates/
│   ├── base.html                    # Base template (loads global CSS/JS)
│   ├── pages/                       # 25 page templates (HAVE INLINE STYLES)
│   │   ├── index.html
│   │   ├── avatars.html            # Largest: 38KB with ~181+ inline styles
│   │   ├── elo.html
│   │   └── ...
│   ├── components/                  # 3 reusable components
│   │   ├── navbar.html
│   │   ├── footer.html
│   │   └── ...
│   └── errors/                      # Error page templates
│
├── static/
│   ├── css/
│   │   ├── components/              # 10 component CSS files (GOOD)
│   │   │   ├── avatar-grid.css
│   │   │   ├── navbar.css
│   │   │   └── ...
│   │   ├── pages/                   # 1 page CSS file (INCOMPLETE)
│   │   │   └── deck_snapshot.css
│   │   ├── global.css               # Global styles
│   │   ├── style.css                # Legacy catch-all (UNCLEAR PURPOSE)
│   │   ├── utilities.css            # Utility classes
│   │   └── tailwind.*.css           # Tailwind build files
│   │
│   ├── js/
│   │   ├── components/              # 5 component JS files (GOOD)
│   │   │   ├── navbar.js
│   │   │   ├── deck-viewer.js
│   │   │   └── ...
│   │   ├── main.js                  # Global JavaScript
│   │   └── [NO pages/ DIRECTORY]   # MISSING - page-specific JS goes here
│   │
│   └── images/                      # Static images
│
├── routes/                          # Flask routes (unchanged by this feature)
├── services/                        # Business logic (unchanged)
└── repositories/                    # Data access (unchanged)
```

**Structure Decision**: This is a web application with server-side rendering (Flask + Jinja2). The refactoring focuses on the `templates/` and `static/` directories. The backend code (routes/services/repositories) is unaffected. The goal is to:

1. Extract inline styles from `templates/pages/` to matching files in `static/css/pages/`
2. Extract inline JS handlers from templates to matching files in `static/js/pages/` (directory needs to be created)
3. Establish clear 1:1 mapping between template files and their CSS/JS assets
4. Consolidate scattered global styles (currently split between global.css, style.css, utilities.css)

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

**Status**: N/A - No constitution exists and this refactoring simplifies rather than complicates the codebase.

---

## Phase 0: Research ✅ COMPLETE

**Output**: [research.md](research.md)

**Key Decisions**:

1. **Inline Style Extraction**: Progressive page-by-page extraction with CSS class creation
   - Start with largest pages (avatars.html - 90+ inline styles)
   - Create reusable CSS classes for repeated patterns
   - Use CSS custom properties for dynamic values

2. **JavaScript Handler Extraction**: Event delegation with module pattern
   - Use `data-*` attributes instead of inline handlers
   - One event listener per interaction type via delegation
   - Module pattern with `DOMContentLoaded` wrapper

3. **File Naming/Organization**: Mirror template structure
   - `templates/pages/avatars.html` → `static/css/pages/avatars.css` + `static/js/pages/avatars.js`
   - Clear categories: `base/`, `components/`, `pages/`, `utilities/` (CSS) and `core/`, `components/`, `pages/`, `utils/` (JS)

4. **Dynamic Styles**: CSS custom properties + data attributes
   - CSS variables for runtime colors/sizes: `style="--avatar-color: {{ color }}"`
   - Data attributes for JavaScript data: `data-chart-data="{{ data|tojson }}"`
   - Limited inline styles only for truly dynamic content (URLs, gradients)

5. **Migration Strategy**: Incremental with visual regression testing
   - One page per commit
   - Screenshot before/after for visual comparison
   - Testing checklist per page (filters, forms, charts)

6. **Global Styles**: Consolidate into `base/` and `utilities/` structure
   - Audit and categorize existing `global.css`, `style.css`, `utilities.css`
   - Migrate page-specific styles to `pages/` directory
   - Delete `style.css` when empty (goal: eliminate legacy catch-all file)

7. **Documentation**: Developer guide + templates + PR checklist
   - Quickstart guide for adding new pages
   - Contract defining mandatory conventions
   - PR checklist to enforce standards

**All Research Questions Resolved** - No remaining "NEEDS CLARIFICATION" items.

---

## Phase 1: Design & Contracts ✅ COMPLETE

**Outputs**:
- [data-model.md](data-model.md) - Entity definitions and relationships
- [contracts/frontend-conventions.md](contracts/frontend-conventions.md) - Developer-facing contract
- [quickstart.md](quickstart.md) - Quick start guide for developers

### Data Model

Defined 4 core entities:
1. **Template File**: Jinja2 HTML templates (pages/components)
2. **CSS File**: Stylesheets organized by scope (base/components/pages/utilities)
3. **JavaScript File**: Scripts organized by scope (core/components/pages/utils)
4. **Asset Loading Directive**: Jinja2 blocks (`{% block styles/scripts %}`)

**Key Relationships**:
- Template ↔ CSS: 1:1 mapping (by name)
- Template ↔ JS: 1:1 mapping (by name, when interactive)
- Template → Template: many:1 (extends base.html) and many:many (includes components)

**Validation Rules**:
- Zero inline `style` attributes (enforced via grep)
- Zero inline JavaScript handlers (enforced via grep)
- File names must match exactly (template name = CSS name = JS name)
- Load order must follow: vendor → base → utilities → components → pages

### Contracts

**Frontend Conventions Contract v1.0.0** defines:

**5 Mandatory Rules**:
1. Zero inline styles (exceptions: truly dynamic URLs/gradients only)
2. Zero inline JavaScript (use event delegation with `data-*` attributes)
3. File naming convention (kebab-case, match template names)
4. Directory structure (CSS: base/components/pages/utilities, JS: core/components/pages/utils)
5. Asset loading (page-specific assets via `{% block styles/scripts %}`)

**3 Developer Workflows**:
1. Adding a new page (create template + CSS + JS + route)
2. Adding a new component (create template + CSS + JS + include)
3. Refactoring existing page (extract inline → external files)

**Code Review Checklist** (12 items):
- CSS/styling checks (no inline styles, correct naming, correct category)
- JavaScript checks (no inline handlers, event delegation, defer attribute)
- Template checks (extends base, uses blocks, no duplicates)
- Testing checks (visual comparison, interactive features, console errors)

### Quickstart Guide

Provides step-by-step instructions for adding a new page:
- Template boilerplate with all required blocks
- CSS boilerplate with header comment and organized rules
- JavaScript boilerplate with event delegation and DOMContentLoaded wrapper
- Compliance checks (grep commands for inline styles/JS)
- Common patterns (loading data, form handling, dynamic styles)
- Troubleshooting guide

**Time to Complete**: ~10-15 minutes for first page

---

## Implementation Readiness

**Status**: ✅ **READY FOR TASKS**

**Next Command**: `/speckit.tasks` to generate actionable task breakdown

**Artifacts Created**:
- ✅ spec.md (feature specification)
- ✅ plan.md (this file)
- ✅ research.md (7 technical decisions)
- ✅ data-model.md (4 entities, validation rules)
- ✅ contracts/frontend-conventions.md (developer contract v1.0.0)
- ✅ quickstart.md (developer onboarding guide)

**Success Metrics** (from spec):
- Developers locate component styles in <30 seconds (baseline: 2-3 min)
- Zero inline styles/JS handlers (baseline: 181+ styles, 15+ handlers)
- Code review time reduces by 40%
- New developers add pages in <15 minutes

**Scope**:
- 31 templates to refactor (25 pages priority, 3 components, 3 other)
- ~25 new CSS files to create in `static/css/pages/`
- ~15 new JS files to create in `static/js/pages/`
- Consolidate 3 global CSS files into organized `base/` and `utilities/` structure
- Create documentation and developer guides

**Risks Mitigated**:
- ✅ Incremental approach limits blast radius
- ✅ Visual regression testing catches styling bugs
- ✅ Per-page commits enable selective rollback
- ✅ Clear conventions prevent future inline style creep
