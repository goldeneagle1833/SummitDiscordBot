// The Explorer Series has its own mini-site under one path. Everything that
// links to an Explorer page goes through these, so the paths live in one place.
export const ES_BASE = '/explorer-series'

export const ES_PATHS = {
  home: ES_BASE,
  standings: `${ES_BASE}/standings`,
  events: `${ES_BASE}/events`,
  host: `${ES_BASE}/host`,
  shop: `${ES_BASE}/shop`,
  applications: `${ES_BASE}/admin/applications`,
  calendar: `${ES_BASE}/admin/calendar`,
}

// The Explorer team's storefront (repositories/store.py KEY_STOREFRONTS). It
// shows in the mini-site's Shop instead of as a tab on /store.
export const ES_STOREFRONT_SLUG = 'explorer-series'

export const ES_LOGO = '/static/images/explorer-series/logo.webp'
export const ES_COMPASS = '/static/images/explorer-series/compass.webp'

export function isExplorerSitePath(pathname) {
  return pathname === ES_BASE || pathname.startsWith(`${ES_BASE}/`)
}
