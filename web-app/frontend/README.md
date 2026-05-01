# Summit Discord Bot — React Frontend

## Local Development Setup

**Prerequisites:**
- Node.js 18+
- Flask backend running on `localhost:5000`

```bash
npm install
npm run dev
```

The Vite dev server starts on `localhost:5173`. It proxies the following paths to Flask at `localhost:5000`:

- `/api/*`
- `/avatar-images/*`
- `/card-images/*`
- `/static/*`
- `/discord`
- `/google`
- `/logout`
- `/auth`

## Build

```bash
npm run build
```

Output goes to `dist/`. Target is **<200KB gzipped** for the initial bundle.

## Project Structure

```
src/
  api/          Centralized fetch client and all API call functions
  components/   Reusable UI components (layout, ui, player, deck, leaderboard)
  context/      AuthContext for user session management
  pages/        Page components (thin — compose from components + api)
```

## Auth Flow

Authentication is Flask session-based using an HttpOnly cookie with `SameSite=Lax`.

- All fetch calls include `credentials: 'include'` via `api/client.js`.
- `/api/me` returns the current user or 401 if unauthenticated.
- OAuth is initiated via `/discord` and `/google` Flask routes. Callbacks redirect to `FRONTEND_URL`.

## Key Conventions

- **No barrel files** — use direct imports, no `index.js` re-exports.
- **No TypeScript** — plain JavaScript throughout.
- **Lazy loading** — heavy components (`DeckViewer`, `CurioTracking`) use `React.lazy()`.
- **Centralized fetch** — all API calls go through `api/client.js`. Never use raw `fetch()`.
- **Tailwind CSS v3** — uses a custom color palette aligned with the main project.
