# Quickstart: Adding a New Page to the Web App

**Last Updated**: 2026-03-08
**For**: Developers working on Summit Discord Bot web application

## Overview

This guide shows you how to add a new page to the web app following the modernized frontend structure. You'll create a template, CSS file, and JavaScript file (if needed), all organized according to our conventions.

**Time to Complete**: ~10-15 minutes for your first page

---

## Prerequisites

- ✅ Web app running locally (`python web-app/app.py`)
- ✅ Familiarity with Flask and Jinja2 templating
- ✅ Basic HTML, CSS, and JavaScript knowledge

---

## Step 1: Create the Template

**Location**: `web-app/templates/pages/`

Create a new HTML file with a descriptive, kebab-case name:

```bash
cd web-app
touch templates/pages/my-new-page.html
```

**Template Boilerplate**:

```html
{% extends "base.html" %}

{% block title %}My New Page - Sorcerers Summit{% endblock %}

{% block styles %}
<!-- Page-specific CSS -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/my-new-page.css') }}?v={{ app_version }}">
{% endblock %}

{% block content %}
<div class="container">
    <h1 class="page-title">My New Page</h1>

    <section class="content-section">
        <p>Page content goes here.</p>

        <!-- Example: Button with data attribute (not onclick) -->
        <button
            class="btn btn-primary"
            data-action="load-data"
            data-source="api">
            Load Data
        </button>
    </section>
</div>
{% endblock %}

{% block scripts %}
<!-- Page-specific JavaScript -->
<script src="{{ url_for('static', filename='js/pages/my-new-page.js') }}?v={{ app_version }}" defer></script>
{% endblock %}
```

**Key Points**:
- ✅ Extends `base.html` (all pages do this)
- ✅ Uses `{% block styles %}` for page-specific CSS
- ✅ Uses `{% block scripts %}` for page-specific JavaScript
- ✅ Includes `?v={{ app_version }}` for cache busting
- ✅ Uses `data-*` attributes instead of `onclick` handlers
- ❌ No inline `style=` attributes

---

## Step 2: Create the CSS File

**Location**: `web-app/static/css/pages/`

Create a CSS file with the **exact same name** as your template (without `.html`):

```bash
touch static/css/pages/my-new-page.css
```

**CSS Boilerplate**:

```css
/*
 * Page: My New Page
 * Template: templates/pages/my-new-page.html
 * Description: Styles specific to the my-new-page view
 */

/* Container Styles */
.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

/* Page Title */
.page-title {
    font-size: 2rem;
    font-weight: 700;
    color: var(--color-text-primary);
    margin-bottom: 1.5rem;
}

/* Content Section */
.content-section {
    background: rgba(255, 255, 255, 0.05);
    padding: 1.5rem;
    border-radius: 8px;
    margin-bottom: 1rem;
}

/* Buttons (example) */
.btn {
    padding: 0.75rem 1.5rem;
    border-radius: 6px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-primary {
    background: var(--color-primary);
    color: white;
    border: none;
}

.btn-primary:hover {
    background: var(--color-primary-dark);
    transform: translateY(-2px);
}
```

**Key Points**:
- ✅ Use CSS classes, not inline styles
- ✅ Use CSS custom properties (`var(--color-primary)`) for theming
- ✅ Include header comment documenting the file's purpose
- ✅ Organize rules logically (container → headings → sections → components)

---

## Step 3: Create the JavaScript File (If Needed)

**Location**: `web-app/static/js/pages/`

If your page has interactivity, create a JavaScript file:

```bash
touch static/js/pages/my-new-page.js
```

**JavaScript Boilerplate**:

```javascript
/**
 * Page: My New Page
 * Template: templates/pages/my-new-page.html
 * Description: Handles interactivity for the my-new-page view
 */

document.addEventListener('DOMContentLoaded', () => {
    initializePage();
});

/**
 * Initialize page functionality
 */
function initializePage() {
    setupEventListeners();
    // Add other initialization here
}

/**
 * Set up event listeners using event delegation
 */
function setupEventListeners() {
    // Event delegation pattern (listen on document, filter by data-action)
    document.addEventListener('click', handleClick);
}

/**
 * Handle all click events on the page
 * @param {Event} e - Click event
 */
function handleClick(e) {
    // Check if clicked element has data-action="load-data"
    const loadBtn = e.target.closest('[data-action="load-data"]');
    if (loadBtn) {
        handleLoadData(loadBtn);
        return;
    }

    // Add more click handlers here
}

/**
 * Handle loading data from API
 * @param {HTMLElement} button - The button that was clicked
 */
function handleLoadData(button) {
    const source = button.dataset.source; // Get data-source attribute

    console.log(`Loading data from: ${source}`);

    // Example: Fetch data from API
    fetch(`/api/${source}`)
        .then(response => response.json())
        .then(data => {
            console.log('Data loaded:', data);
            // Update page with data
        })
        .catch(error => {
            console.error('Error loading data:', error);
        });
}
```

**Key Points**:
- ✅ Wrap all code in `DOMContentLoaded` event listener
- ✅ Use event delegation (listen on document, filter by selector)
- ✅ Use `data-*` attributes to identify elements, not IDs or `onclick`
- ✅ Document functions with JSDoc comments
- ❌ No inline JavaScript in templates

---

## Step 4: Create the Flask Route

**Location**: `web-app/routes/pages.py`

Add a route to serve your new page:

```python
@bp.route('/my-new-page')
def my_new_page():
    """Render the my new page view."""
    return render_template(
        'pages/my-new-page.html',
        # Pass any data needed by the template
        page_data={'example': 'value'}
    )
```

---

## Step 5: Test Your Page

### 5.1 Visual Check

1. **Start the web app**:
   ```bash
   python web-app/app.py
   ```

2. **Navigate to your page**:
   ```
   http://localhost:5000/my-new-page
   ```

3. **Verify**:
   - ✅ Page loads without errors
   - ✅ Styles are applied correctly
   - ✅ Interactive features work (buttons, forms, etc.)
   - ✅ Browser console shows no JavaScript errors

### 5.2 Compliance Check

**Check for inline styles** (should return 0):
```bash
grep 'style=' web-app/templates/pages/my-new-page.html
```

**Check for inline JavaScript** (should return 0):
```bash
grep -E 'on(click|change|load)=' web-app/templates/pages/my-new-page.html
```

**Verify file naming**:
```bash
# Template exists
ls web-app/templates/pages/my-new-page.html

# CSS file exists and matches name
ls web-app/static/css/pages/my-new-page.css

# JS file exists and matches name (if created)
ls web-app/static/js/pages/my-new-page.js
```

---

## Common Patterns

### Pattern 1: Loading Data on Page Load

```javascript
// In static/js/pages/my-new-page.js

document.addEventListener('DOMContentLoaded', async () => {
    await loadInitialData();
});

async function loadInitialData() {
    try {
        const response = await fetch('/api/my-data');
        const data = await response.json();

        // Update page with data
        renderData(data);
    } catch (error) {
        console.error('Failed to load data:', error);
    }
}

function renderData(data) {
    const container = document.getElementById('data-container');
    container.innerHTML = data.items.map(item => `
        <div class="data-item">${item.name}</div>
    `).join('');
}
```

### Pattern 2: Form Handling

```html
<!-- In template -->
<form data-form="submit-example" class="example-form">
    <input type="text" name="username" placeholder="Username" required>
    <button type="submit" class="btn btn-primary">Submit</button>
</form>
```

```javascript
// In JavaScript
document.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-form="submit-example"]');
    if (!form) return;

    e.preventDefault(); // Prevent default form submission

    const formData = new FormData(form);
    const username = formData.get('username');

    // Submit via AJAX
    fetch('/api/submit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username})
    })
    .then(response => response.json())
    .then(data => console.log('Success:', data))
    .catch(error => console.error('Error:', error));
});
```

### Pattern 3: Dynamic Styles with CSS Variables

```html
<!-- In template: Set CSS variable from server data -->
<div class="chart-container" style="--chart-height: {{ chart_height }}px;">
    <canvas id="chart"></canvas>
</div>
```

```css
/* In CSS: Use the variable */
.chart-container {
    height: var(--chart-height, 400px); /* 400px fallback */
    background: rgba(255, 255, 255, 0.05);
    padding: 1rem;
}
```

---

## Troubleshooting

### Issue: Styles Not Loading

**Symptom**: Page appears unstyled or uses only global styles.

**Solution**:
1. Check that CSS file exists: `ls static/css/pages/my-new-page.css`
2. Verify file name matches template name exactly
3. Check browser DevTools Network tab for 404 errors
4. Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
5. Verify `{% block styles %}` is in template

### Issue: JavaScript Not Running

**Symptom**: Buttons don't work, console shows errors.

**Solution**:
1. Check browser console for errors (F12)
2. Verify JS file exists: `ls static/js/pages/my-new-page.js`
3. Ensure `defer` attribute is on `<script>` tag
4. Check that code is wrapped in `DOMContentLoaded` listener
5. Verify selectors match elements in HTML

### Issue: "ReferenceError: app_version is not defined"

**Symptom**: Template error when loading assets.

**Solution**:
- Ensure `app_version` is passed to template by Flask route
- Check that `from utils.version import APP_VERSION` exists in app.py
- Verify route includes `app_version=APP_VERSION` in render_template()

---

## Next Steps

Now that you've created your first page, try:

1. **Adding a Component**: Create a reusable component in `templates/components/`
2. **Using Tailwind Utilities**: Leverage Tailwind classes for quick styling
3. **Fetching API Data**: Integrate with backend APIs in `routes/api/`
4. **Reading the Full Contract**: See `contracts/frontend-conventions.md` for all rules

---

## Need Help?

- **Examples**: Check `templates/pages/about.html` for a simple, clean page example
- **Contract**: See `specs/001-web-app-restructure/contracts/frontend-conventions.md`
- **Data Model**: See `specs/001-web-app-restructure/data-model.md` for entity relationships
- **Research**: See `specs/001-web-app-restructure/research.md` for technical decisions

---

## Summary Checklist

Before submitting your PR, verify:

- [ ] Template extends `base.html`
- [ ] Template name matches CSS/JS filenames
- [ ] CSS file in `static/css/pages/`
- [ ] JS file in `static/js/pages/` (if needed)
- [ ] No inline `style` attributes (grep returns 0)
- [ ] No inline `onclick`/event handlers (grep returns 0)
- [ ] Assets loaded via `{% block styles %}` and `{% block scripts %}`
- [ ] Cache busting query param `?v={{ app_version }}` on all assets
- [ ] Page tested visually in browser
- [ ] Browser console shows no errors

**You're ready to go!** 🚀
