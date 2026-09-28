// Formatting helpers shared by the Card Win Rates page pieces.

export const percent = (value, digits = 1) =>
  value == null ? '—' : `${(value * 100).toFixed(digits)}%`

// Win rates are colored by how far they sit from a coin flip.
export function winRateTone(value) {
  if (value == null) return 'muted'
  if (value >= 0.53) return 'good'
  if (value <= 0.47) return 'bad'
  return 'mid'
}

export const TONE_TEXT = {
  good: 'text-[#3fb950]',
  mid: 'text-[#e3b341]',
  bad: 'text-[#f85149]',
  muted: 'text-text-muted',
}

export const TONE_BAR = {
  good: 'bg-[#3fb950]',
  mid: 'bg-[#e3b341]',
  bad: 'bg-[#f85149]',
  muted: 'bg-text-muted',
}

// Percentage-point difference, e.g. +8.4 pp.
export function ppLabel(difference) {
  if (difference == null) return '—'
  const rounded = Math.round(difference * 1000) / 10
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : ''
  return `${sign}${Math.abs(rounded).toFixed(1)} pp`
}

export const gamesLabel = (count) =>
  count == null ? 'under 20 games' : `${count.toLocaleString()} ${count === 1 ? 'game' : 'games'}`

export const shortDate = (ms) =>
  new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

// Same normalization the vendored table uses for its catalog index.
export const nameKey = (value) =>
  String(value || '').toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

export function lookupCard(catalogIndex, card) {
  return catalogIndex.get(card.cardKey) ?? catalogIndex.get(nameKey(card.cardName))
}
