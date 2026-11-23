/**
 * Every badge a profile's hero card can show, best first, each with the key
 * the player's "Profile badges" setting stores.
 *
 * The hero card shows the player's best 3 by default, so it never gets
 * crowded; the rest are one tap away in the Postseason tab, which always
 * lists everything. A player can pick their own set instead.
 */

export const DEFAULT_SHOWN = 3

const FINISH_WEIGHT = { Champion: 10, Winner: 12, Finalist: 20, 'Top 4': 30, 'Top 8': 40, 'Top 16': 50 }
const finishWeight = (label) => FINISH_WEIGHT[label] ?? (/^Top \d+/.test(label || '') ? 55 : 60)

// "Summit Gothic Season 4" -> { set: 'gothic', num: '4' }
function seasonOf(name) {
  const m = /(?:([a-z]+)\s+)?season\s+(\d+)/i.exec(name || '')
  return m ? { set: (m[1] || '').toLowerCase(), num: m[2] } : null
}

/**
 * A paper result for one of Summit's own seasons (an event on the Top 8 page
 * like "Summit Gothic Season 4") repeats the postseason bracket finish the
 * player already has for that season, so the badges show it only once.
 */
function repeatsPostseason(finish, marks) {
  if (!/summit|tts/i.test(finish.event || '')) return false
  const season = seasonOf(finish.event)
  if (!season) return false
  return (marks?.entries || []).some((e) => {
    const s = seasonOf(e.name)
    return s && s.num === season.num && (!s.set || !season.set || s.set === season.set)
  })
}

export function profileBadges({ marks, honours = [], paperFinishes = [], eventBadges = [] }) {
  const out = []
  if (marks?.best_label) {
    out.push({ kind: 'postseason', key: 'postseason', group: 'Postseason', label: marks.best_label, detail: 'Best postseason finish', weight: finishWeight(marks.best_label) })
  }
  if (marks?.limited_best_label) {
    out.push({ kind: 'postseason', key: 'postseason_limited', group: 'Postseason', label: marks.limited_best_label, detail: 'Best Limited postseason finish', weight: finishWeight(marks.limited_best_label) + 2 })
  }
  if (marks?.underdog_best_label) {
    out.push({ kind: 'postseason', key: 'postseason_underdog', group: 'Postseason', label: marks.underdog_best_label, detail: 'Best Underdog bracket finish', weight: finishWeight(marks.underdog_best_label) + 4 })
  }
  if (honours.length) {
    const best = honours.reduce((a, b) => (b.place < a.place ? b : a))
    out.push({
      kind: 'honour',
      place: best.place,
      title: honours.map((h) => h.title).filter(Boolean).join('\n') || `${best.season} ${best.label}`,
      key: 'avatar_honours',
      group: 'Season avatar honours',
      label: best.label,
      detail: `${best.season}${honours.length > 1 ? ` (+${honours.length - 1} more)` : ''}`,
      weight: 5 + best.place * 10,
    })
  }
  for (const b of eventBadges) {
    out.push({ kind: 'event', avatar: b.avatar, title: b.title, key: eventBadgeKey(b), group: 'Top avatar at an event', label: b.label, detail: b.event, weight: 18 })
  }
  for (const f of paperFinishes) {
    if (repeatsPostseason(f, marks)) continue
    out.push({ kind: 'paper', title: f.title || `${f.label} · ${f.event}`, key: paperBadgeKey(f), group: 'Paper tournament finishes', label: f.label, detail: f.event, weight: finishWeight(f.label) + 1 })
  }
  // Best first; ties keep the order above (newest first within each kind)
  return out
    .map((b, i) => ({ ...b, order: i }))
    .sort((a, b) => a.weight - b.weight || a.order - b.order)
}

/**
 * The keys the hero card shows.
 * shown: the player's own pick (a list), or null for the default best 3.
 * hidden: an older setting (badges switched off); still honoured with the default.
 */
export function heroBadgeKeys(badges, shown = null, hidden = []) {
  if (Array.isArray(shown)) {
    const have = new Set(badges.map((b) => b.key))
    return new Set(shown.filter((k) => have.has(k)))
  }
  const off = new Set(hidden || [])
  return new Set(badges.filter((b) => !off.has(b.key)).slice(0, DEFAULT_SHOWN).map((b) => b.key))
}

export function eventBadgeKey(b) {
  return `event_avatar:${b.folder}:${b.avatar}`
}

export function paperBadgeKey(f) {
  return `paper:${f.folder}`
}
