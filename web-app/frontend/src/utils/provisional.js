/**
 * Provisional ratings (Glicko-2 ladders).
 *
 * A rating with fewer than PROVISIONAL_GAMES games comes back from the API as
 * `null` with `provisional: true, provisional_games: n` (or prefixed names such
 * as `event_provisional` / `lifetime_provisional` on the player profile). A
 * per-match change from a side's first 8 games comes back as `null` with a
 * sibling `<field>_hidden: true`. Old Elo data carries no flags and is shown
 * exactly as before.
 */
export const PROVISIONAL_GAMES = 8
export const HIDDEN_CHANGE_TITLE = `Provisional: shown after ${PROVISIONAL_GAMES} games`

export function provisionalLabel(games) {
  return `Provisional (${games ?? 0}/${PROVISIONAL_GAMES})`
}

/** Provisional info for a rating on `obj`. prefix '' -> `provisional`, 'event' -> `event_provisional`. */
export function provisionalOf(obj, prefix = '') {
  const key = prefix ? `${prefix}_provisional` : 'provisional'
  if (!obj || obj[key] !== true) return null
  return { games: obj[`${key}_games`] ?? 0 }
}

export function isProvisional(obj, prefix = '') {
  return provisionalOf(obj, prefix) !== null
}

/** True when `obj[field]` is a per-match change/after value hidden while provisional. */
export function isHidden(obj, field) {
  return obj?.[`${field}_hidden`] === true
}

/** Number with a leading "+" for positive values ("+12", "-8", "0"). */
export function signed(value) {
  const n = Number(value)
  return n > 0 ? `+${n}` : `${n}`
}

/** True when a rating/change is a real number that can be displayed, summed or charted. */
export function isNum(value) {
  return value != null && Number.isFinite(Number(value))
}
