/**
 * Date-window math for the Elements page timeline.
 *
 * The API sends sparse per-day counts; we turn each series into running
 * totals over one shared date axis so any window is one subtraction.
 */

const ELEMENTS = ['Fire', 'Water', 'Earth', 'Air']

/** Every ISO day from the earliest to the latest across the given date lists. */
export function mergeDates(...lists) {
  const all = lists.flat().filter(Boolean).sort()
  if (!all.length) return []
  const out = []
  const [y1, m1, d1] = all[0].split('-').map(Number)
  const last = all[all.length - 1]
  const cur = new Date(Date.UTC(y1, m1 - 1, d1))
  for (;;) {
    const iso = cur.toISOString().slice(0, 10)
    out.push(iso)
    if (iso >= last) break
    cur.setUTCDate(cur.getUTCDate() + 1)
  }
  return out
}

/** {key: {date: n}} → {key: running totals aligned to dates}. */
export function buildCumulative(dates, series) {
  const out = {}
  for (const [key, byDay] of Object.entries(series || {})) {
    const running = new Array(dates.length)
    let sum = 0
    dates.forEach((d, i) => {
      sum += byDay[d] || 0
      running[i] = sum
    })
    out[key] = running
  }
  return out
}

/** Sum of a running-total series over the `days`-long window ending at `end` (null days = everything so far). */
export function windowSum(running, end, days) {
  if (!running || end < 0) return 0
  const before = days == null || end - days < 0 ? 0 : running[end - days]
  return running[end] - before
}

/** Per-series totals for a window, highest first, zeros dropped. */
export function countsAt(cumulative, end, days) {
  const rows = []
  for (const [name, running] of Object.entries(cumulative)) {
    const count = windowSum(running, end, days)
    if (count > 0) rows.push({ name, count })
  }
  return rows.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
}

/** Timeline API days ({date: {group: {key: [w, l]}}}) → flat series keyed "group|key|w" / "group|key|l". */
export function flattenElementDays(days) {
  const series = {}
  for (const [date, groups] of Object.entries(days || {})) {
    for (const [group, entries] of Object.entries(groups)) {
      for (const [key, [w, l]] of Object.entries(entries)) {
        const wk = `${group}|${key}|w`
        const lk = `${group}|${key}|l`
        if (w) (series[wk] ||= {})[date] = w
        if (l) (series[lk] ||= {})[date] = l
      }
    }
  }
  return series
}

const rate = (wins, total) => Math.round((total > 0 ? (wins / total) * 100 : 50) * 10) / 10
const pct = (n, d) => Math.round((d > 0 ? (n / d) * 100 : 0) * 10) / 10

/**
 * Rebuild the /api/elements response shape for one window, so the existing
 * charts render unchanged: elements, dominant, splash, combinations, composition.
 */
export function elementStatsAt(cumulative, end, days) {
  const wl = (group, key) => {
    const wins = windowSum(cumulative[`${group}|${key}|w`], end, days)
    const losses = windowSum(cumulative[`${group}|${key}|l`], end, days)
    return { name: key, wins, losses, total: wins + losses, win_rate: rate(wins, wins + losses) }
  }

  const base = ELEMENTS.map((el) => wl('el', el))
  const totalWins = base.reduce((s, e) => s + e.wins, 0)
  const totalLosses = base.reduce((s, e) => s + e.losses, 0)
  const elements = base.map((e) => ({
    ...e,
    win_presence: pct(e.wins, totalWins),
    loss_presence: pct(e.losses, totalLosses),
  }))

  const keysIn = (group) => [...new Set(
    Object.keys(cumulative).filter((k) => k.startsWith(`${group}|`)).map((k) => k.split('|')[1]),
  )]

  const hasSplash = keysIn('spl').length > 0
  const combos = keysIn('combo').map((c) => wl('combo', c)).filter((c) => c.total > 0)
  const comboTotal = combos.reduce((s, c) => s + c.total, 0)

  return {
    elements,
    dominant: ELEMENTS.map((el) => wl('dom', el)),
    splash: hasSplash ? ELEMENTS.map((el) => wl('spl', el)) : [],
    combinations: combos.filter((c) => c.total >= 3).sort((a, b) => b.total - a.total),
    composition: combos
      .map((c) => ({ elements: c.name, count: c.total, percent: pct(c.total, comboTotal) }))
      .sort((a, b) => b.count - a.count),
  }
}
