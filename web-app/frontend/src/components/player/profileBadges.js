/**
 * Every badge a profile's hero card can show, each with the key the player's
 * "Profile badges" setting stores when they hide it. Hidden badges stay in
 * the Postseason tab; only the hero card leaves them out.
 */
export function profileBadges({ marks, honours = [], paperFinishes = [], eventBadges = [] }) {
  const out = []
  if (marks?.best_label) {
    out.push({ key: 'postseason', group: 'Postseason', label: marks.best_label, detail: 'Best postseason finish' })
  }
  if (marks?.limited_best_label) {
    out.push({ key: 'postseason_limited', group: 'Postseason', label: marks.limited_best_label, detail: 'Best Limited postseason finish' })
  }
  if (marks?.underdog_best_label) {
    out.push({ key: 'postseason_underdog', group: 'Postseason', label: marks.underdog_best_label, detail: 'Best Underdog bracket finish' })
  }
  if (honours.length) {
    const best = honours.reduce((a, b) => (b.place < a.place ? b : a))
    out.push({
      key: 'avatar_honours',
      group: 'Season avatar honours',
      label: best.label,
      detail: `${best.season}${honours.length > 1 ? ` (+${honours.length - 1} more)` : ''}`,
    })
  }
  for (const b of eventBadges) {
    out.push({ key: `event_avatar:${b.folder}:${b.avatar}`, group: 'Top avatar at an event', label: b.label, detail: b.event })
  }
  for (const f of paperFinishes) {
    out.push({ key: `paper:${f.folder}`, group: 'Paper tournament finishes', label: f.label, detail: f.event })
  }
  return out
}

export const eventBadgeKey = (b) => `event_avatar:${b.folder}:${b.avatar}`
export const paperBadgeKey = (f) => `paper:${f.folder}`
