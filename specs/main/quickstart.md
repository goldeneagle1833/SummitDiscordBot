# Quickstart: Flask/Jinja2 → React SPA Migration

## What This Feature Does

Replaces the Jinja2 server-side rendering with a React SPA at `web-app/frontend/`. Flask becomes a pure JSON API backend. The React app is built with Vite, styled with Tailwind CSS v4, and routes via React Router v6. Auth (Discord + Google OAuth) continues through Flask sessions — the React app calls `/api/me` on load to hydrate user state.

---

## Prerequisites

- Python 3.11+ with existing `web-app/` dependencies installed
- Node.js 20+ (`node --version`)
- The existing Flask app runs on `http://localhost:5000`

---

## Local Development Setup

### 1. Start Flask API backend

```bash
cd web-app
source venv/bin/activate           # or: venv\Scripts\activate on Windows
python app.py
# Flask runs on http://localhost:5000
```

### 2. Start React dev server (separate terminal)

```bash
cd web-app/frontend
npm install                        # first time only
npm run dev
# Vite runs on http://localhost:5173
# /api/* requests are proxied → Flask :5000
```

Open `http://localhost:5173` — the React app with live HMR.

### 3. Environment variables (optional for local dev)

Create `web-app/frontend/.env.local`:
```
VITE_API_BASE_URL=http://localhost:5000
```

The `api/client.js` reads `import.meta.env.VITE_API_BASE_URL` (defaults to empty string, relying on Vite proxy).

---

## Building for Production

```bash
cd web-app/frontend
npm ci
npm run build
# Output: web-app/frontend/dist/
```

Nginx serves `dist/index.html` for all non-API routes (catch-all `try_files`).

---

## Project Structure Quick Reference

```
web-app/frontend/src/
├── api/           # All fetch calls live here — import these in pages
│   ├── client.js  # Base fetch wrapper (credentials, error handling)
│   ├── auth.js    # getMe(), logout()
│   ├── leaderboard.js
│   ├── players.js
│   ├── matches.js
│   ├── events.js
│   └── decks.js
├── context/
│   └── AuthContext.jsx   # useAuth() hook — access user anywhere
├── components/   # Shared UI — import directly (no barrel files)
│   ├── layout/Nav.jsx
│   ├── layout/Footer.jsx
│   ├── player/PlayerCard.jsx
│   ├── deck/DeckViewer.jsx      # lazy-loaded
│   ├── leaderboard/LeaderboardTable.jsx
│   └── ui/Button.jsx, Avatar.jsx, Badge.jsx, Spinner.jsx
└── pages/        # One file per route — thin, compose components
```

---

## Adding a New Page

1. Create `src/pages/MyPage.jsx`
2. Add any new API calls to the appropriate `src/api/*.js` file
3. Add a `<Route>` in `src/App.jsx`
4. Link from `Nav.jsx` if needed

---

## Adding a New API Endpoint

1. Add to appropriate `src/api/*.js` module (e.g., `players.js` for player endpoints)
2. Use the `client.get()` / `client.post()` wrapper — never raw `fetch()`
3. The api module is the only place that knows about endpoint URLs

---

## Auth in Components

```jsx
import { useAuth } from '@/context/AuthContext'

function MyComponent() {
  const { user, loading } = useAuth()

  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" />

  return <div>Hello, {user.username}</div>
}
```

---

## Tailwind CSS

Use utility classes directly in JSX. No separate CSS files for component styles.

```jsx
<button className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg">
  Click me
</button>
```

Custom design tokens (colors, fonts) are in `tailwind.config.js` — copied from the existing web app palette.

---

## Common Gotchas

- **Session cookies**: All `fetch()` calls must use `credentials: 'include'` (handled by `api/client.js` automatically)
- **No barrel files**: Import directly from the file path — `import PlayerCard from '@/components/player/PlayerCard'`, not from an index
- **OAuth in dev**: Login flows go through `/discord` and `/google` routes, proxied to Flask. The callback redirects to `FRONTEND_URL` (defaults to `http://localhost:5173` in dev)
- **Deep links in dev**: React Router handles routing — navigating to `/player/123` directly works because Vite's dev server handles `history` mode
