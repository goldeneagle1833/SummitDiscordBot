# Life Counter Layout Debugging Guide

## Issue Summary
1. **Threshold elements stacking vertically** instead of horizontal grid
2. **Plus/minus buttons not working** - no counter updates

---

## Visual Wireframe

### CURRENT STATE (BROKEN)
```
┌─────────────────────────────────────┐
│   Life Counter          [Reset]     │
├─────────────────────────────────────┤
│           Threshold                 │
│                                     │
│  ┌──────────────────────────┐      │  ← Each element is
│  │    [-]  💧  [+]          │      │    its own row
│  │         0                │      │    (WRONG!)
│  └──────────────────────────┘      │
│                                     │
│  ┌──────────────────────────┐      │
│  │    [-]  🔥  [+]          │      │
│  │         0                │      │
│  └──────────────────────────┘      │
│                                     │
│  ┌──────────────────────────┐      │
│  │    [-]  🌍  [+]          │      │
│  │         0                │      │
│  └──────────────────────────┘      │
│                                     │
│  ┌──────────────────────────┐      │
│  │    [-]  💨  [+]          │      │
│  │         0                │      │
│  └──────────────────────────┘      │
└─────────────────────────────────────┘
```

### EXPECTED STATE (FIXED)
```
┌──────────────────────────────────────────────────────────┐
│   Life Counter                             [Reset]       │
├──────────────────────────────────────────────────────────┤
│                     Threshold                            │
│  ┌──────────┬──────────┬──────────┬──────────┐         │
│  │  [-] 💧  │  [-] 🔥  │  [-] 🌍  │  [-] 💨  │         │
│  │   0 [+]  │   0 [+]  │   0 [+]  │   0 [+]  │         │
│  └──────────┴──────────┴──────────┴──────────┘         │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │     [-5]  [-1]    20    [+1]  [+5]        │         │
│  │              (Opponent)                    │         │
│  └────────────────────────────────────────────┘         │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │     [-5]  [-1]    20    [+1]  [+5]        │         │
│  │               (You)                        │         │
│  └────────────────────────────────────────────┘         │
│                                                          │
│  ┌──────────┬──────────┬──────────┬──────────┐         │
│  │  [-] 💧  │  [-] 🔥  │  [-] 🌍  │  [-] 💨  │         │
│  │   0 [+]  │   0 [+]  │   0 [+]  │   0 [+]  │         │
│  └──────────┴──────────┴──────────┴──────────┘         │
│                     Threshold                            │
└──────────────────────────────────────────────────────────┘
```

---

## Fixes Applied

### 1. CSS Grid Force Override
**File**: `web-app/static/css/pages/life_counter.css`

```css
/* Added !important to override Tailwind/base CSS */
.threshold-elements {
  display: grid !important;
  grid-template-columns: repeat(4, 1fr) !important;
  gap: 0.5rem;
  width: 100%;
}

.threshold-element {
  display: flex !important;
  flex-direction: row !important;
  /* ... */
  min-width: 0; /* Prevents grid overflow */
}
```

### 2. JavaScript Debug Logging
**File**: `web-app/static/js/pages/life_counter.js`

Added console logging to track:
- Button click events
- State updates
- DOM element counts

### 3. Event Handling Fix
Added `preventDefault()` and `stopPropagation()` to button clicks to prevent event bubbling issues.

---

## Testing Instructions

### Step 1: Open Browser Console
1. Open the life counter page in browser
2. Press **F12** to open Developer Tools
3. Go to **Console** tab

### Step 2: Check Console Output
You should see:
```
[LifeCounter] DOM loaded, initializing...
[LifeCounter] State loaded: {version: "1.0", ...}
[LifeCounter] Initialization complete
[LifeCounter] Threshold elements: 8
[LifeCounter] Element buttons: 16
[LifeCounter] Found 16 element counter buttons
```

### Step 3: Test Grid Layout
- Threshold elements should be **4 columns side-by-side** (not stacked)
- Each element has: [−] button, icon, counter, [+] button

### Step 4: Test Button Clicks
Click any +/− button. Console should show:
```
[LifeCounter] Button clicked: player=player1, element=water, amount=1
[LifeCounter] Updated player1 water: 0 → 1
```

The counter value should visually update on screen.

---

## Debug Test Page

Open: `web-app/static/test_layout.html` in browser

This isolated test page shows:
- ✅ Grid layout working correctly (green border)
- ✅ Button clicks working
- ✅ Counter updates

If this works but the main page doesn't, there's a CSS conflict in `base.html`.

---

## Common Issues

### Issue: Grid still stacking vertically
**Solution**: Check if parent container has `display: block` or `flex-direction: column`. Inspect element in DevTools:
1. Right-click `.threshold-elements`
2. Inspect → Computed styles
3. Check `display` value (should be `grid`)

### Issue: Buttons not clicking
**Solution**: Check console for errors. Possible causes:
- JavaScript not loaded (404 error)
- Event listeners not attached (should see "Found X buttons")
- CSS `pointer-events: none` blocking clicks

### Issue: Counter updates but doesn't show
**Solution**: Check `renderUI()` is selecting correct elements:
```javascript
// Should find 8 spans (4 per player)
document.querySelectorAll('.element-counter-value').length
```

---

## Browser DevTools Inspection

### Check Grid Layout
1. Right-click on threshold section
2. Inspect Element
3. Look for `.threshold-elements` div
4. In Computed styles, verify:
   - `display: grid`
   - `grid-template-columns: repeat(4, 1fr)`

### Check Event Listeners
1. Select any +/− button in Elements tab
2. Event Listeners panel (right side)
3. Should see `click` event attached

---

## Next Steps

If issues persist after fixes:
1. Hard refresh browser (Ctrl+Shift+R) to clear CSS cache
2. Check Network tab for CSS/JS loading errors
3. Verify HTML structure matches expected wireframe
4. Test in different browser (Chrome vs Firefox)

---

**Files Modified**:
- `web-app/static/css/pages/life_counter.css`
- `web-app/static/js/pages/life_counter.js`

**Test File Created**:
- `web-app/static/test_layout.html`
