/**
 * Deck links come from two places:
 *   - sorcerytcg.com (formerly curiosa.io): https://sorcerytcg.com/decks/<id>
 *   - Play Sorcery Online, which hosts its own decks:
 *     https://playsorceryonline.com/?deck=<id>
 *
 * Mirrors services/curiosa.py on the backend, which is the source of truth
 * for what counts as a deck link.
 */

const PSO_HOST = 'playsorceryonline.com'
const CURIOSA_HOSTS = ['sorcerytcg.com', 'curiosa.io']
const PSO_DECK_ID_RE = /^[A-Za-z0-9_-]{6,}$/

function hostMatches(hostname, host) {
  const h = (hostname || '').toLowerCase()
  return h === host || h.endsWith('.' + host)
}

function parse(url) {
  if (!url || typeof url !== 'string') return null
  try {
    const parsed = new URL(url.trim())
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
    return parsed
  } catch {
    return null
  }
}

/** The deck id from a Play Sorcery Online deck link, or null. */
export function getPsoDeckId(url) {
  const parsed = parse(url)
  if (!parsed || !hostMatches(parsed.hostname, PSO_HOST)) return null
  const id = (parsed.searchParams.get('deck') || '').trim()
  return PSO_DECK_ID_RE.test(id) ? id : null
}

/** The canonical share link for a PSO-hosted deck. */
export function psoDeckUrl(deckId) {
  return `https://${PSO_HOST}/?deck=${deckId}`
}

/** 'sorcery_online', 'curiosa', or null for anything else. */
export function getDeckSource(url) {
  if (getPsoDeckId(url)) return 'sorcery_online'
  const parsed = parse(url)
  if (parsed && CURIOSA_HOSTS.some((h) => hostMatches(parsed.hostname, h))) return 'curiosa'
  return null
}

/** Where a deck link points, for a "View on ..." label. */
export function getDeckSourceLabel(url) {
  const source = getDeckSource(url)
  if (source === 'sorcery_online') return 'Sorcery Online'
  if (source === 'curiosa') return 'Curiosa'
  return 'deck site'
}

export const DECK_URL_PLACEHOLDER = 'https://sorcerytcg.com/decks/... or https://playsorceryonline.com/?deck=...'
