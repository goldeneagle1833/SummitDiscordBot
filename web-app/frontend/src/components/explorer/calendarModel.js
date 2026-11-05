// Builds the Explorer events calendar from applications and their date rows.
// Pure functions, so the rules are easy to test and tweak.

// Two events on the same weekend closer than this split the same players.
export const COMPETING_MILES = 100
// A date window longer than this ("June", "summer") is soft demand: shown,
// but never counted as a clash.
const EXACT_MAX_DAYS = 7
// More than this many exact events on one weekend is worth a look anyway.
export const BUSY_WEEKEND = 3

const DAY_MS = 86400000
const toDate = (iso) => new Date(`${iso}T00:00:00Z`)
const iso = (d) => d.toISOString().slice(0, 10)
const addDays = (d, n) => new Date(d.getTime() + n * DAY_MS)

/** Monday of the week holding this date (weeks run Monday to Sunday). */
export function weekStart(d) {
  const day = d.getUTCDay() // 0 Sun .. 6 Sat
  return addDays(d, -((day + 6) % 7))
}

/** Great-circle distance in miles, or null if either point is missing. */
export function milesBetween(a, b) {
  if ([a?.latitude, a?.longitude, b?.latitude, b?.longitude].some((v) => v == null)) return null
  const rad = (x) => (x * Math.PI) / 180
  const dLat = rad(b.latitude - a.latitude)
  const dLon = rad(b.longitude - a.longitude)
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLon / 2) ** 2
  return 3958.8 * 2 * Math.asin(Math.sqrt(h))
}

/**
 * Turn applications into weeks.
 *
 * Returns [{ start, saturday, sunday, exact: [entry], flexible: [entry],
 *            competing: [{a, b, miles}], busy }]
 * covering March to October of `year` (stretched if any date falls outside).
 * An entry is { application, row, rank }.
 */
export function buildCalendar(applications, { year = 2027, firstChoiceOnly = false } = {}) {
  const entries = []
  applications.forEach((application) => {
    ;(application.dates || []).forEach((row, i) => {
      if (!row.start_date) return
      const rank = row.choice_rank || i + 1
      if (firstChoiceOnly && rank !== 1) return
      entries.push({ application, row, rank })
    })
  })

  let first = toDate(`${year}-03-01`)
  let last = toDate(`${year}-10-31`)
  entries.forEach(({ row }) => {
    const s = toDate(row.start_date)
    const e = toDate(row.end_date || row.start_date)
    if (s < first && s.getUTCFullYear() >= year - 1) first = s
    if (e > last && e.getUTCFullYear() <= year + 1) last = e
  })

  const weeks = []
  for (let w = weekStart(first); w <= last; w = addDays(w, 7)) {
    weeks.push({
      start: iso(w),
      saturday: iso(addDays(w, 5)),
      sunday: iso(addDays(w, 6)),
      exact: [],
      flexible: [],
      competing: [],
      busy: false,
    })
  }
  const byStart = new Map(weeks.map((w) => [w.start, w]))

  entries.forEach((entry) => {
    const s = toDate(entry.row.start_date)
    const e = toDate(entry.row.end_date || entry.row.start_date)
    const exact = (e - s) / DAY_MS < EXACT_MAX_DAYS
    for (let w = weekStart(s); w <= e; w = addDays(w, 7)) {
      const week = byStart.get(iso(w))
      if (!week) continue
      ;(exact ? week.exact : week.flexible).push(entry)
    }
  })

  weeks.forEach((week) => {
    // One application listing two dates in the same week counts once.
    const seen = new Set()
    week.exact = week.exact.filter((e) => {
      if (seen.has(e.application.id)) return false
      seen.add(e.application.id)
      return true
    })
    week.flexible = week.flexible.filter((e) => !seen.has(e.application.id))
    for (let i = 0; i < week.exact.length; i += 1) {
      for (let j = i + 1; j < week.exact.length; j += 1) {
        const a = week.exact[i]
        const b = week.exact[j]
        const miles = milesBetween(a.application, b.application)
        if (miles != null && miles < COMPETING_MILES) week.competing.push({ a, b, miles })
      }
    }
    week.busy = week.exact.length > BUSY_WEEKEND
  })

  return weeks
}

/** Which entries in a week are part of a competing pair. */
export function competingIds(week) {
  const ids = new Set()
  week.competing.forEach(({ a, b }) => { ids.add(a.application.id); ids.add(b.application.id) })
  return ids
}
