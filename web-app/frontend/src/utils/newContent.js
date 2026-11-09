// New-content dots in the menu: a small white dot next to a link when its page
// has something new the person hasn't opened yet (Bruce, 2026-11-09).
//
// The server sends, per page key, when its newest content appeared. "Seen" is
// saved to the account when logged in (so it follows the person between
// devices) and in this browser's storage otherwise.

// Page key -> the paths that count as opening that page
export const NEW_CONTENT_PAGES = {
  'top-8': ['/top-8'],
  'deck-rec': ['/deck-rec'],
  'deck-archetypes': ['/deck-archetypes'],
  'meta-report': ['/meta-report'],
  avatars: ['/avatars'],
  'card-stats': ['/card-stats'],
  articles: ['/articles'],
  brackets: ['/brackets'],
  explorer: ['/explorer'],
  store: ['/store'],
}

export const SEEN_STORAGE_KEY = 'summit-nav-seen'

// The page key a menu link points at, or null
export function pageKeyForPath(pathname) {
  if (!pathname) return null
  for (const [key, paths] of Object.entries(NEW_CONTENT_PAGES)) {
    if (paths.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return key
  }
  return null
}

function toMs(value) {
  const ms = value ? Date.parse(value) : NaN
  return Number.isNaN(ms) ? null : ms
}

// Newer of two seen maps, key by key
export function mergeSeen(a, b) {
  const out = { ...(a || {}) }
  for (const [key, value] of Object.entries(b || {})) {
    const mine = toMs(out[key])
    const theirs = toMs(value)
    if (theirs !== null && (mine === null || theirs > mine)) out[key] = value
  }
  return out
}

// Set of page keys whose newest content is newer than when they were seen
export function newPageKeys(latest, seen) {
  const keys = new Set()
  for (const [key, value] of Object.entries(latest || {})) {
    const latestMs = toMs(value)
    if (latestMs === null) continue
    const seenMs = toMs(seen?.[key])
    if (seenMs === null || seenMs < latestMs) keys.add(key)
  }
  return keys
}

export function loadLocalSeen() {
  try {
    const raw = localStorage.getItem(SEEN_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function saveLocalSeen(seen) {
  try {
    localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify(seen))
  } catch {}
}
