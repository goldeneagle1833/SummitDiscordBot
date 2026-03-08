# Feature Specification: Web App Structure Modernization

**Feature Branch**: `001-web-app-restructure`
**Created**: 2026-03-08
**Status**: Draft
**Input**: User description: "the web app folder and file struture is not great, the html has javascript in it. and the folder structue is not a modern standard. both of these things makes it hard to follow and devople for"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Frontend Developer Locates Assets Quickly (Priority: P1)

A frontend developer joins the project and needs to modify the styling for the avatar cards component. They should be able to navigate directly to the relevant CSS file without searching through multiple files or reading inline styles within HTML templates.

**Why this priority**: Developer productivity is the primary goal of this refactoring. If developers can't find code quickly, every task takes longer, and the codebase becomes harder to maintain.

**Independent Test**: Can be fully tested by timing how long it takes a new developer to locate and modify a specific component's styling. Success = finding the right file in under 30 seconds.

**Acceptance Scenarios**:

1. **Given** a developer needs to modify avatar card styling, **When** they navigate to the CSS directory, **Then** they find a clearly named file (e.g., `components/avatar-card.css`) containing all avatar card styles
2. **Given** a developer needs to add interactivity to a page, **When** they check the JavaScript directory, **Then** they find a file matching the page name with all relevant event handlers
3. **Given** a developer reviews an HTML template, **When** they open the file, **Then** they see only HTML structure with no inline `style` attributes or `onclick` handlers

---

### User Story 2 - Eliminate Inline Styles from Templates (Priority: P1)

All HTML templates must have zero inline `style` attributes. Currently there are 181+ inline styles that make the HTML difficult to read and maintain, violating separation of concerns.

**Why this priority**: This is the core technical debt causing maintainability issues. Inline styles prevent CSS reusability, make global design changes difficult, and bloat HTML files.

**Independent Test**: Can be fully tested by running a grep search for `style=` in template files and verifying zero matches. Delivers immediate improvement in template readability.

**Acceptance Scenarios**:

1. **Given** any HTML template file, **When** searching for inline `style=` attributes, **Then** zero instances are found
2. **Given** a designer wants to update spacing globally, **When** they modify CSS variables or classes, **Then** changes apply across all components without editing HTML
3. **Given** a developer reviews a template diff during code review, **When** they check changed lines, **Then** they see only structural HTML changes, not style changes

---

### User Story 3 - Eliminate Inline JavaScript from Templates (Priority: P1)

All HTML templates must have zero inline event handlers (onclick, onload, etc.). Currently there are 15+ inline handlers that should be moved to external JavaScript files with proper event listeners.

**Why this priority**: Inline JavaScript violates Content Security Policy best practices, makes code harder to test, and prevents proper JavaScript bundling and minification.

**Independent Test**: Can be fully tested by searching for `onclick=`, `onload=`, and similar patterns in templates. Delivers better security and testability.

**Acceptance Scenarios**:

1. **Given** any HTML template file, **When** searching for inline event handlers (`onclick=`, `onchange=`, etc.), **Then** zero instances are found
2. **Given** a developer needs to debug a click handler, **When** they open the corresponding JavaScript file, **Then** they find all event listeners clearly defined with proper selectors
3. **Given** a security audit of the application, **When** checking for CSP violations, **Then** no inline JavaScript is detected in templates

---

### User Story 4 - Standardize Asset Organization (Priority: P2)

The static assets (CSS, JavaScript, images) should follow a clear, predictable naming convention that mirrors the component/page structure in templates.

**Why this priority**: Once inline code is removed, organizing the extracted files logically is essential for maintainability. However, this can happen after extraction is complete.

**Independent Test**: Can be fully tested by verifying file naming matches template structure (e.g., `templates/pages/avatars.html` → `static/css/pages/avatars.css` → `static/js/pages/avatars.js`).

**Acceptance Scenarios**:

1. **Given** a page template at `templates/pages/[name].html`, **When** looking for its assets, **Then** corresponding files exist at `static/css/pages/[name].css` and `static/js/pages/[name].js`
2. **Given** a component template at `templates/components/[name].html`, **When** looking for its assets, **Then** corresponding files exist at `static/css/components/[name].css` and `static/js/components/[name].js`
3. **Given** a developer adds a new page template, **When** they create associated assets, **Then** the file structure naturally guides them to the correct location

---

### User Story 5 - Documentation for New Structure (Priority: P3)

Create clear documentation explaining the new folder structure, naming conventions, and best practices for adding new pages/components.

**Why this priority**: Documentation ensures the refactoring effort isn't wasted. Without it, developers might revert to old patterns. However, this comes after structural changes are complete.

**Independent Test**: Can be fully tested by asking a new developer to add a new page following only the documentation, then verifying they created files in the correct locations.

**Acceptance Scenarios**:

1. **Given** a developer reads the project documentation, **When** they need to add a new page, **Then** the documentation clearly explains where to place HTML, CSS, and JavaScript files
2. **Given** a code review of a new feature, **When** checking file organization, **Then** all files follow the documented conventions
3. **Given** a team onboarding session, **When** presenting the frontend architecture, **Then** the documentation provides clear diagrams or examples of the structure

---

### Edge Cases

- What happens when a page requires multiple JavaScript modules (e.g., charts, forms, tables)? Should they be separate files or bundled?
- How does the system handle shared styles between multiple pages (currently some in `global.css`, some in `utilities.css`, some inline)?
- What happens to CSS that is truly dynamic (generated from Python/Jinja2 variables)? Can it be extracted to CSS variables?
- How are third-party libraries (Tailwind, Chart.js) organized relative to custom code?
- What happens when a template uses both Tailwind utility classes and custom styles? Should all custom styles be in external CSS?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST contain zero inline `style` attributes in any HTML template files (current count: 181+)
- **FR-002**: System MUST contain zero inline JavaScript event handlers (`onclick`, `onchange`, `onload`, etc.) in any HTML template files (current count: 15+)
- **FR-003**: Every page template MUST have clearly identifiable corresponding CSS files that can be located through consistent naming conventions
- **FR-004**: Every page template that requires interactivity MUST have clearly identifiable corresponding JavaScript files that can be located through consistent naming conventions
- **FR-005**: Every reusable component template MUST have clearly identifiable corresponding CSS files that can be located through consistent naming conventions
- **FR-006**: Every reusable component template that requires interactivity MUST have clearly identifiable corresponding JavaScript files that can be located through consistent naming conventions
- **FR-007**: JavaScript event handlers MUST be defined in external JavaScript files, not inline within HTML templates
- **FR-008**: All visual styling MUST be defined in external CSS files, not inline within HTML templates
- **FR-009**: Dynamic styles that depend on runtime data MUST use declarative styling mechanisms that can be configured from external stylesheets
- **FR-010**: Common styles and scripts that apply across multiple pages MUST be loaded through a shared mechanism to avoid duplication
- **FR-011**: Page-specific and component-specific assets MUST be loaded on-demand for the pages/components that need them (not globally)
- **FR-012**: CSS files MUST be organized into clear, predictable categories based on their scope (global, component-specific, page-specific, utilities)
- **FR-013**: JavaScript files MUST be organized into clear, predictable categories based on their scope (core, component-specific, page-specific, utilities)
- **FR-014**: Documentation MUST be created explaining the organizational structure, naming conventions, and guidelines for adding new pages/components

### Key Entities *(include if feature involves data)*

- **CSS File**: Represents styling for a page, component, or global scope. Organized by scope with clear naming conventions. Maps 1:1 with template files.
- **JavaScript File**: Represents behavior/interactivity for a page, component, or global scope. Organized by scope with clear naming conventions. Maps 1:1 with template files (when needed).
- **Template File**: HTML template representing a page or reusable component. Contains only HTML structure and templating syntax, no inline styles or scripts.
- **Asset Loading Mechanism**: Defines which CSS/JS files need to be loaded for each page, allowing page-specific and component-specific assets to be loaded on-demand rather than globally.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can locate any component's styles or scripts in under 30 seconds (baseline: currently takes 2-3 minutes searching through inline styles and multiple CSS files)
- **SC-002**: Zero inline `style` attributes exist in any template file (baseline: 181+ instances)
- **SC-003**: Zero inline JavaScript event handlers exist in any template file (baseline: 15+ instances)
- **SC-004**: 100% of pages and components follow the standardized file naming and organization convention
- **SC-005**: Code review time for frontend changes reduces by 40% due to clearer separation of concerns (baseline: reviewers must check HTML diffs with mixed styling changes)
- **SC-006**: New developers can add a new page following the structure in under 15 minutes with documentation alone (no mentoring required)
- **SC-007**: CSS file count is reduced by consolidating scattered styles (baseline: unclear ownership across style.css, global.css, utilities.css, inline styles)
- **SC-008**: Template file sizes reduce by an average of 30-40% after removing inline styles

## Assumptions

- **Assumption 1**: Tailwind CSS will remain as the utility framework and does not need to be removed (utility classes in HTML are acceptable, inline `style=` attributes are not)
- **Assumption 2**: The Flask/Jinja2 template system will remain (not migrating to a JavaScript framework like React/Vue)
- **Assumption 3**: Existing page functionality must be preserved during refactoring (no behavior changes, only structural improvements)
- **Assumption 4**: Browser support targets remain the same (no new CSS features that require polyfills)
- **Assumption 5**: Asset versioning via `?v={{ app_version }}` query parameters will continue to handle cache busting
- **Assumption 6**: Build process changes (if needed for bundling/minification) are out of scope for this feature (manual reorganization first, optimization later)

## Dependencies

- **Dependency 1**: All inline styles must be extracted before CSS file organization can be standardized (cannot organize files that don't exist yet)
- **Dependency 2**: Understanding which styles are shared vs. page-specific requires analyzing current inline styles and CSS files
- **Dependency 3**: Testing all pages after refactoring requires access to all application states (login, admin, various data scenarios)

## Out of Scope

- **Migrating to a JavaScript framework** (React, Vue, Svelte) - this is a structural refactoring only
- **Asset bundling/build process** (Webpack, Vite, Parcel) - may be addressed in a future feature
- **CSS preprocessor adoption** (SASS, LESS) - current vanilla CSS/Tailwind setup is sufficient
- **Automated testing for frontend** (Jest, Playwright) - focus is on structure, not test coverage
- **Design system creation** - while better organization enables this, creating a formal design system is a separate initiative
- **Performance optimization** - minification, compression, lazy loading are out of scope
- **Accessibility improvements** - focus is on code organization, not adding ARIA attributes or keyboard navigation

## Success Metrics Tracking

Track the following during and after implementation:

1. **Code quality**:
   - Number of inline `style` attributes (target: 0, baseline: 181+)
   - Number of inline event handlers (target: 0, baseline: 15+)
   - Number of CSS files (consolidated from scattered sources)

2. **Developer productivity**:
   - Time to locate a component's styles (target: <30 seconds)
   - Time to add a new page following conventions (target: <15 minutes)
   - Code review time for frontend PRs (target: 40% reduction)

3. **Maintainability**:
   - Template file sizes (target: 30-40% reduction)
   - Consistency score: % of templates following naming conventions (target: 100%)

## Risks

- **Risk 1**: Dynamic styles generated from server-side variables may be difficult to extract to external stylesheets (mitigation: use declarative styling mechanisms that can be configured externally)
- **Risk 2**: Large refactoring increases risk of introducing visual bugs (mitigation: systematic page-by-page testing and visual comparison)
- **Risk 3**: Existing inline styles may be duplicated across templates without clear ownership (mitigation: audit and consolidate duplicates during extraction)
- **Risk 4**: Team may revert to old patterns without clear guidelines (mitigation: create comprehensive documentation and establish code quality checks)
