import { useState } from 'react'
import { STATUS_COLORS } from './statusColors'
import { competingIds } from './calendarModel'

const DAY_MS = 86400000
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const toDate = (iso) => new Date(`${iso}T00:00:00Z`)
const iso = (d) => d.toISOString().slice(0, 10)

const who = (a) =>
  a.lgs_name || [a.first_name, a.last_name].filter(Boolean).join(' ') || a.discord_handle || `#${a.id}`

/**
 * Per-day lookups from the week model: the exact events on each day, how
 * many flexible windows cover it, and which days hold a competing event.
 */
function indexDays(weeks) {
  const days = new Map()
  const get = (key) => {
    if (!days.has(key)) days.set(key, { exact: [], flexible: 0, competing: false })
    return days.get(key)
  }
  weeks.forEach((week) => {
    const clashing = competingIds(week)
    const weekEnd = toDate(week.sunday)
    const weekStart = toDate(week.start)
    week.exact.forEach((entry) => {
      const s = toDate(entry.row.start_date)
      const e = toDate(entry.row.end_date || entry.row.start_date)
      for (let d = s; d <= e; d = new Date(d.getTime() + DAY_MS)) {
        if (d < weekStart || d > weekEnd) continue
        const day = get(iso(d))
        day.exact.push(entry)
        if (clashing.has(entry.application.id)) day.competing = true
      }
    })
    week.flexible.forEach((entry) => {
      const s = toDate(entry.row.start_date)
      const e = toDate(entry.row.end_date)
      for (let d = weekStart; d <= weekEnd; d = new Date(d.getTime() + DAY_MS)) {
        if (d >= s && d <= e) get(iso(d)).flexible += 1
      }
    })
  })
  return days
}

function monthsFor(weeks) {
  const keys = []
  weeks.forEach((w) => {
    ;[w.start, w.sunday].forEach((d) => {
      const key = d.slice(0, 7)
      if (!keys.includes(key)) keys.push(key)
    })
  })
  // Weeks spill a few days into the month before and after; keep months
  // that hold at least one Saturday of the range.
  return keys.filter((key) => weeks.some((w) => w.saturday.startsWith(key)))
}

function DayCell({ date, inMonth, day, selected, onSelect }) {
  const n = day?.exact.length || 0
  const soft = day?.flexible || 0
  const weekend = [0, 6].includes(toDate(date).getUTCDay())
  if (!inMonth) return <div className="min-h-[3.25rem] sm:min-h-[5.5rem]" />
  return (
    <button
      type="button"
      onClick={() => onSelect(selected ? null : date)}
      aria-label={`${date}: ${n} event${n === 1 ? '' : 's'}${day?.competing ? ', competing' : ''}`}
      aria-pressed={selected}
      className={`relative min-h-[3.25rem] sm:min-h-[5.5rem] rounded border p-1 text-left align-top transition-colors overflow-hidden ${
        day?.competing
          ? 'border-red-400/80 bg-red-400/10'
          : selected
            ? 'border-secondary'
            : 'border-border/60 hover:border-secondary/60'
      } ${weekend ? 'bg-bg-surface' : 'bg-bg-base'}`}
      style={soft && !day?.competing ? { boxShadow: `inset 0 -${Math.min(soft, 4) * 3}px 0 rgba(167,139,250,0.35)` } : undefined}
    >
      <div className={`text-[11px] leading-none ${n ? 'text-text-primary font-semibold' : 'text-text-muted'}`}>
        {toDate(date).getUTCDate()}
      </div>
      {/* Names on wide screens, dots on phones. */}
      <ul className="hidden sm:block mt-1 space-y-0.5">
        {day?.exact.slice(0, 3).map((entry) => (
          <li key={entry.application.id} className="flex items-center gap-1 text-[10px] leading-tight">
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: STATUS_COLORS[entry.application.status] || '#9ca3af' }}
            />
            <span className={`truncate ${entry.rank === 1 ? 'text-text-primary' : 'text-text-muted'}`}>
              {who(entry.application)}
            </span>
          </li>
        ))}
        {n > 3 && <li className="text-[10px] text-text-muted">+{n - 3} more</li>}
      </ul>
      {n > 0 && (
        <div className="sm:hidden flex flex-wrap gap-0.5 mt-1">
          {day.exact.slice(0, 4).map((entry) => (
            <span
              key={entry.application.id}
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: STATUS_COLORS[entry.application.status] || '#9ca3af' }}
            />
          ))}
        </div>
      )}
    </button>
  )
}

function DayDetail({ date, day }) {
  const label = toDate(date).toLocaleDateString('en-US', {
    timeZone: 'UTC', weekday: 'long', month: 'long', day: 'numeric',
  })
  return (
    <div className="border-t border-border p-3 space-y-2" aria-label="Selected day">
      <div className="text-sm text-text-primary">{label}</div>
      {day?.competing && <div className="text-xs text-red-400">Competing events within 100 miles this weekend</div>}
      {day?.exact.length ? (
        <ul className="space-y-1">
          {day.exact.map((entry) => (
            <li key={entry.application.id} className="flex flex-wrap items-center gap-x-2 text-xs">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: STATUS_COLORS[entry.application.status] || '#9ca3af' }}
              />
              <span className="text-text-primary">{who(entry.application)}</span>
              <span className="text-text-muted">
                {[entry.application.city, entry.application.state].filter(Boolean).join(', ')}
                {' · '}choice {entry.rank}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-text-muted">No exact dates on this day.</p>
      )}
      {day?.flexible > 0 && (
        <p className="text-xs text-violet-300">
          {day.flexible} flexible window{day.flexible === 1 ? '' : 's'} (like “mid-June”) cover this day.
        </p>
      )}
    </div>
  )
}

/** Wall-calendar view of the same weeks the list view shows. */
export default function MonthGrid({ weeks }) {
  const [selected, setSelected] = useState(null)
  const days = indexDays(weeks)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {monthsFor(weeks).map((key) => {
        const first = toDate(`${key}-01`)
        const lead = (first.getUTCDay() + 6) % 7
        const length = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate()
        const cells = []
        for (let i = 0; i < lead; i += 1) cells.push({ key: `lead-${i}`, inMonth: false })
        for (let d = 1; d <= length; d += 1) {
          const date = `${key}-${String(d).padStart(2, '0')}`
          cells.push({ key: date, date, inMonth: true })
        }
        const selectedHere = selected && selected.startsWith(key)
        return (
          <section key={key} className="bg-bg-raised border border-border rounded-lg overflow-hidden">
            <h2 className="px-3 py-2 text-sm font-semibold text-secondary border-b border-border">
              {first.toLocaleDateString('en-US', { timeZone: 'UTC', month: 'long', year: 'numeric' })}
            </h2>
            <div className="p-2">
              <div className="grid grid-cols-7 gap-1 mb-1">
                {WEEKDAYS.map((d) => (
                  <div key={d} className="text-[10px] text-center text-text-muted">{d}</div>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {cells.map((cell) => (
                  <DayCell
                    key={cell.key}
                    date={cell.date}
                    inMonth={cell.inMonth}
                    day={cell.date ? days.get(cell.date) : null}
                    selected={cell.date === selected}
                    onSelect={setSelected}
                  />
                ))}
              </div>
            </div>
            {selectedHere && <DayDetail date={selected} day={days.get(selected)} />}
          </section>
        )
      })}
    </div>
  )
}
