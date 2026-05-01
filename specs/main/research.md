# Research: Flask/Jinja2 → React SPA Migration

## R-1: Tailwind CSS Version

**Decision**: Tailwind CSS v4 via `@tailwindcss/vite` plugin
**Rationale**: Tailwind v4 ships a native Vite plugin that eliminates PostCSS from the critical path, delivering faster HMR and build times. The `@tailwindcss/vite` plugin injects CSS as a Vite virtual module — no `postcss.config.js` required (though one can coexist). CSS custom properties replace `tailwind.config.js` theme keys in v4's new cascade-layer system.
**Alternatives considered**:
- Tailwind v3 + PostCSS: Mature, widely documented, but slower build pipeline. Rejected because v4 is current and the Vite plugin path is simpler.
- Vanilla CSS / CSS Modules: Rejected — spec explicitly requires Tailwind only.

## R-2: React Router Version

**Decision**: React Router v6 (data router / `createBrowserRouter`)
**Rationale**: v6 is stable and widely adopted. The data router API (`createBrowserRouter` + `loader`) enables parallel data loading at the route level without waterfalls, matching the spec requirement for `Promise.all` fetching. v7 introduces breaking changes not worth taking during a migration.
**Alternatives considered**:
- React Router v5: Legacy API. Rejected.
- TanStack Router: Type-safe but spec says no TypeScript. Rejected.

## R-3: Flask Sessions + SPA (Credentials: Include)

**Decision**: Use `credentials: 'include'` on all `fetch()` calls; Vite proxy for dev (no flask-cors needed)
**Rationale**: Flask session cookies are `HttpOnly`, `Secure`, and `SameSite=Lax` (already configured in `app.py`). In production, the React app and Flask API share the same Nginx origin — cookies are sent automatically, no CORS needed. In development, the Vite `proxy` config forwards `/api/**` to Flask on `:5000`, keeping requests same-origin from the browser's perspective.
**Alternatives considered**:
- JWT: Rejected by spec.
- flask-cors for dev: Unnecessary with proxy. Rejected.
- flask-cors for prod: Insecure (broadens CORS surface). Rejected.

## R-4: /api/me Endpoint

**Decision**: Add `GET /api/me` to Flask that reads from `session`
**Rationale**: The React `AuthContext` needs to know the current user on every page load without a redirect. Returns session user if authenticated, `401` if not.

**Response shapes**:
```json
// 200 OK (authenticated)
{ "user_id": "123456789", "username": "DragonSlayer", "avatar": "https://cdn.discordapp.com/...", "auth_provider": "discord" }

// 401 Unauthorized (no session)
{ "error": "Not authenticated" }
```

## R-5: Vite Proxy Configuration

**Decision**: Configure `server.proxy` in `vite.config.js` to forward all Flask routes to `http://localhost:5000`
**Rationale**: Single-origin in dev = no CORS, no cookie issues, OAuth flows work end-to-end.

```js
proxy: {
  '/api':           'http://localhost:5000',
  '/avatar-images': 'http://localhost:5000',
  '/card-images':   'http://localhost:5000',
  '/static':        'http://localhost:5000',
  '/discord':       { target: 'http://localhost:5000', changeOrigin: true },
  '/google':        { target: 'http://localhost:5000', changeOrigin: true },
  '/logout':        'http://localhost:5000',
}
```

## R-6: Nginx Catch-All for React Router

**Decision**: `try_files $uri $uri/ /index.html` catch-all for all non-API routes
**Rationale**: React Router handles client-side routing. Without this, direct navigation to `/player/123` returns 404.

```nginx
# Specific routes first
location /api/          { proxy_pass http://gunicorn; }
location /avatar-images/ { alias /path/to/avatar_imgs/; }
location /card-images/   { alias /path/to/card_images/; }

# React SPA catch-all LAST
location / {
    root /path/to/web-app/frontend/dist;
    try_files $uri $uri/ /index.html;
}
```

## R-7: Auth Callback Redirect

**Decision**: Replace `url_for("pages.home")` in `auth.py` callbacks with `redirect(FRONTEND_URL)` where `FRONTEND_URL` is an env var
**Rationale**: Post-migration, OAuth callbacks must redirect to the React app root (not Jinja2 pages route). React then calls `/api/me` to hydrate auth state.

**Implementation**: `FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")` in `webapp_config.py`.

## R-8: Build Strategy

**Decision**: Build React on the server during deployment (`npm ci && npm run build` in deploy script)
**Rationale**: Minimal change to existing SSH-based deploy workflow. Node.js must be installed on the Linode server (one-time setup).
**Alternatives considered**:
- Build in CI and upload dist/: Cleaner but requires artifact handling. Can be adopted later.
- Pre-commit dist/: Anti-pattern. Rejected.

## R-9: Lazy Loading Strategy

**Decision**: `React.lazy()` + `<Suspense>` for `DeckViewer` component and `CurioTracking` page
**Rationale**: Both are heavy, behind-the-fold routes rarely hit on first visit. Lazy loading keeps initial bundle under 200KB.

```jsx
const DeckViewer = React.lazy(() => import('@/components/deck/DeckViewer'))
const CurioTracking = React.lazy(() => import('@/pages/CurioTracking'))
```

## R-10: Tailwind Color Palette

**Decision**: Copy `web-app/tailwind.config.js` color tokens verbatim into `web-app/frontend/tailwind.config.js`
**Rationale**: Migration spec requires preserving existing visual design. The web app already has a custom palette — it must be the single source of truth.

## R-11: No Barrel Files

**Decision**: Direct file imports only — no `index.js` re-export files in `components/`
**Rationale**: Barrel files force bundlers to eagerly evaluate all re-exported modules, adding 200-800ms to cold start. Direct imports (`import PlayerCard from '@/components/player/PlayerCard'`) are faster and more explicit.

## R-12: Path Aliases

**Decision**: Configure `@` as alias for `src/` in `vite.config.js`
**Rationale**: Avoids fragile relative path chains (`../../components/...`). Standard Vite pattern.

```js
resolve: { alias: { '@': path.resolve(__dirname, './src') } }
```

## R-13: Events API Route Naming

**Decision**: Rename Flask route from `/api/games` to `/api/events` for consistency with React page names
**Rationale**: The React app has `Events.jsx`, `EventDetail.jsx`, and `api/events.js`. Using `/api/games` as the backend route creates a naming mismatch. Rename to `/api/events` in Flask and update any existing consumers.
**Migration**: Add `/api/events` routes in Flask; optionally keep `/api/games` as a deprecated alias during transition.

## R-14: Jinja2 Parallel Operation

**Decision**: Keep Jinja2 templates and `routes/pages.py` running alongside the React SPA during migration
**Rationale**: Allows incremental rollout — React app can be tested in production while Jinja2 pages remain as fallback. Remove Jinja2 templates only after verifying all React pages work correctly. Nginx serves React `dist/` for non-API routes, but Flask still has the pages blueprint registered (just unreachable behind Nginx catch-all).

## R-15: Admin Pages in React

**Decision**: Migrate admin pages to React with admin authorization checks
**Rationale**: Admin pages (audit log, event management) should be part of the SPA for consistent UX. The `AuthContext` exposes `user.user_id`, and admin checks are done server-side via existing `@require_admin` decorator on API endpoints. React admin pages simply call admin API endpoints — if the user isn't admin, the API returns 403.
**Implementation**: Add `is_admin` field to `/api/me` response so React can conditionally show admin nav links and pages.

## R-16: Static Content Pages

**Decision**: Lightweight React components with hardcoded content (no markdown)
**Rationale**: About, Help, Privacy, Terms pages are simple HTML content. Rebuilding as React components with Tailwind classes preserves the existing visual design while keeping them consistent with the SPA layout (shared Nav/Footer). No markdown parser dependency needed.

## R-17: Life Counter

**Decision**: Rebuild as a standard React component within the SPA
**Rationale**: Keeps all pages consistent in look, feel, and routing. The life counter currently receives session data via template injection — in React, it uses `useAuth()` from `AuthContext` instead. All interactive JS logic is reimplemented as React state.

## R-18: Node.js on Production Server

**Decision**: Install Node.js 20 LTS on Linode as a deployment prerequisite
**Rationale**: Required for `npm ci && npm run build` during deploy. One-time setup task. Use NodeSource or nvm for installation.
**Task**: Add Node.js installation step to deployment documentation.

## Summary

| # | Topic | Decision |
|---|-------|----------|
| R-1 | Tailwind | v4 via @tailwindcss/vite |
| R-2 | React Router | v6 createBrowserRouter |
| R-3 | Auth/CORS | credentials: include + Vite proxy; no flask-cors |
| R-4 | /api/me | New Flask endpoint reading session |
| R-5 | Vite proxy | Forward /api, /avatar-images, /card-images, /discord, /google, /logout |
| R-6 | Nginx | try_files catch-all for React Router |
| R-7 | Auth callbacks | Redirect to FRONTEND_URL env var |
| R-8 | Build | npm ci && npm run build on server during deploy |
| R-9 | Lazy loading | React.lazy() for DeckViewer + CurioTracking |
| R-10 | Colors | Copy from web-app/tailwind.config.js |
| R-11 | No barrels | Direct imports only |
| R-12 | Path aliases | @ → src/ in vite.config.js |
| R-13 | Events API | Rename /api/games → /api/events |
| R-14 | Parallel operation | Keep Jinja2 running alongside React SPA |
| R-15 | Admin pages | Migrate to React with server-side admin checks |
| R-16 | Static pages | Lightweight React components, hardcoded content |
| R-17 | Life Counter | Rebuild as React component in SPA |
| R-18 | Node.js | Install Node 20 LTS on Linode (one-time setup) |
