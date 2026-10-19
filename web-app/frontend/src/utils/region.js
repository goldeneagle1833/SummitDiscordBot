import { get } from '@/api/client'

/**
 * Is this visitor in Europe? Used to show the "Buy on Cardmarket" button.
 *
 * Asks the server first (Cloudflare's CF-IPCountry header). When the server
 * can't tell (local dev, unknown IP), falls back to the browser's time zone.
 * `?cardmarket=1` / `?cardmarket=0` in the URL forces it on or off for testing.
 * The answer is fetched once per page load and shared.
 */
let regionPromise = null

export function europeFromTimeZone(timeZone) {
  return typeof timeZone === 'string' && timeZone.startsWith('Europe/')
}

function forcedByUrl() {
  try {
    const value = new URLSearchParams(window.location.search).get('cardmarket')
    if (value === '1') return true
    if (value === '0') return false
  } catch { /* no window */ }
  return null
}

export function isEuropeanVisitor() {
  const forced = forcedByUrl()
  if (forced !== null) return Promise.resolve(forced)
  if (!regionPromise) {
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
    regionPromise = get('/api/visitor-region')
      .then((r) => (typeof r?.europe === 'boolean' ? r.europe : europeFromTimeZone(timeZone)))
      .catch(() => europeFromTimeZone(timeZone))
  }
  return regionPromise
}
