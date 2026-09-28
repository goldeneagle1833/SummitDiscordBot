# Vendored from Play Sorcery Online's `@sorc/analytics-ui` 0.1.0

Source: the Summit handoff ZIP (PSO release `9b7c6e4`, September 28, 2026).
Only the pieces the Card Win Rates page reuses are here:

- `cardTable.ts` — filtering, column minimums, sorting and paging of the `/cards` rows (unchanged)
- `queryModel.ts`, `population.ts` — query builder model and API types (unchanged)
- `QueryBuilder.tsx` — the AND/OR query builder (unchanged)
- `query.css` — its stylesheet with PSO's green palette swapped for Summit's tokens
  (`web-app/frontend/tailwind.config.js`); selectors and layout are as shipped

The dashboard shell (`index.tsx`, `style.css`) is not vendored: the page is
Summit's own layout. The Next.js proxy (`summitProxy.ts`) is replaced by
`web-app/routes/api/ranked_analytics.py`.

When PSO ships a new handoff, diff the files above against the new `src/`
and re-apply the color swap to `query.css`.
