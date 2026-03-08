# CSS Consolidation Plan

**Date**: 2026-03-08
**Purpose**: Document existing CSS files and plan for reorganization

## Current State

### Existing CSS Files

| File | Size | Lines | Purpose | Status |
|------|------|-------|---------|--------|
| `global.css` | 4.6 KB | 245 | CSS custom properties, base styles | ✅ Well-organized |
| `style.css` | 25 KB | ~700+ | Legacy catch-all file | ⚠️ Needs consolidation |
| `utilities.css` | 4.0 KB | ~120 | Utility classes | ✅ Mostly good |
| `tailwind.output.css` | ~12 KB | N/A | Tailwind build output | 📦 Move to vendor/ |

### global.css Analysis

**Current Contents**:
- ✅ CSS Custom Properties (`:root` variables)
  - Colors (primary, secondary, background, surface, text, status colors)
  - Typography (font-family, font-sizes)
  - Spacing (xs, sm, md, lg, xl)
  - Border radius, shadows, transitions
- ✅ Base HTML resets and typography
- ✅ Global layout utilities

**Migration Plan**:
- Keep CSS custom properties in `base/variables.css`
- Move resets to `base/reset.css`
- Move typography to `base/typography.css`
- Move layout utilities to `base/layout.css`
- **Result**: Delete `global.css` after migration

### style.css Analysis

**Size**: 25 KB (largest file - needs audit)

**Suspected Contents** (to be verified):
- Page-specific styles (should move to `pages/`)
- Component styles (should move to `components/`)
- Utility classes (should move to `utilities/`)
- Duplicates and unused styles

**Migration Plan**:
1. Audit all rules in `style.css`
2. Categorize each rule:
   - Page-specific → `pages/[page].css`
   - Component-specific → `components/[component].css`
   - Utility classes → `utilities/[category].css`
   - Global base → `base/[category].css`
3. **Result**: Delete `style.css` when empty (goal: 0 KB)

### utilities.css Analysis

**Current Contents**:
- Spacing utilities (margins, padding)
- Display utilities (flex, grid, block, inline)
- Text utilities (alignment, color, size)
- Visibility utilities (hidden, visible)

**Migration Plan**:
- Split into organized files:
  - `utilities/spacing.css` - Margin, padding utilities
  - `utilities/colors.css` - Background, text color utilities
  - `utilities/flexbox.css` - Flex utilities
  - `utilities/visibility.css` - Show/hide utilities
- Remove duplicates of Tailwind utilities
- **Result**: Delete `utilities.css` after split

### tailwind.output.css

**Current Location**: `static/css/tailwind.output.css`

**Migration Plan**:
- Move to `static/css/vendor/tailwind.output.css`
- Update `base.html` to load from vendor directory

## Target Structure

```
static/css/
├── base/
│   ├── reset.css        # Browser resets (from global.css)
│   ├── variables.css    # CSS custom properties (from global.css)
│   ├── typography.css   # Font styles, headings (from global.css + style.css)
│   └── layout.css       # Container, grid, layout (from global.css)
├── components/
│   ├── [existing component files - no changes]
├── pages/
│   ├── [new files created in US1]
├── utilities/
│   ├── spacing.css      # Margin, padding (from utilities.css)
│   ├── colors.css       # Background, text colors (from utilities.css + new)
│   ├── flexbox.css      # Flex utilities (from utilities.css)
│   └── visibility.css   # Show/hide (from utilities.css)
└── vendor/
    └── tailwind.output.css  # Moved from root
```

## Load Order (base.html)

```html
<!-- 1. Vendor CSS (external libraries) -->
<link rel="stylesheet" href=".../vendor/tailwind.output.css">

<!-- 2. Base CSS (foundation) -->
<link rel="stylesheet" href=".../base/reset.css">
<link rel="stylesheet" href=".../base/variables.css">
<link rel="stylesheet" href=".../base/typography.css">
<link rel="stylesheet" href=".../base/layout.css">

<!-- 3. Utilities CSS (helper classes) -->
<link rel="stylesheet" href=".../utilities/spacing.css">
<link rel="stylesheet" href=".../utilities/colors.css">
<link rel="stylesheet" href=".../utilities/flexbox.css">
<link rel="stylesheet" href=".../utilities/visibility.css">

<!-- 4. Component CSS (global components) -->
<link rel="stylesheet" href=".../components/navbar.css">
<link rel="stylesheet" href=".../components/[other].css">

<!-- 5. Page CSS (loaded in page templates via blocks) -->
{% block styles %}{% endblock %}
```

## Migration Tasks

### Immediate (Phase 2: Foundational)
- [ ] Split `global.css` → `base/` (reset, variables, typography, layout)
- [ ] Move `tailwind.output.css` → `vendor/`
- [ ] Split `utilities.css` → `utilities/` (spacing, colors, flexbox, visibility)
- [ ] Update `base.html` to load new structure

### Later (Phase 6: US4 - Standardize Organization)
- [ ] Audit `style.css` (25 KB)
- [ ] Migrate page-specific styles → `pages/`
- [ ] Migrate component styles → `components/`
- [ ] Delete `style.css` when empty

## Success Criteria

✅ **After Consolidation**:
- All CSS in one of: `base/`, `components/`, `pages/`, `utilities/`, `vendor/`
- No orphan CSS files in `static/css/` root
- `global.css`, `style.css`, `utilities.css` deleted
- Clear, predictable load order

## Before/After Comparison

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Root CSS files | 4 (global, style, utilities, tailwind) | 0 | ✅ 100% |
| Organized categories | 2 (components, pages) | 5 (base, components, pages, utilities, vendor) | ✅ +3 |
| Largest file size | 25 KB (style.css) | <5 KB per file | ✅ Better modularity |
| Load order clarity | Unclear | Explicit (vendor → base → utilities → components → pages) | ✅ Clear |
