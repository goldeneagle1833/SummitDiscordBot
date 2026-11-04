import { useState } from 'react'
import { STATUS_COLORS } from './statusColors'
import { competingIds } from './calendarModel'

const DAY_MS = 86400000
const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
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
  if (!inMonth) return <div className="h-8" />
  const names = (day?.exact || []).map((e) => who(e.application)).join(', ')
  return (
    <button
      type="button"
      onClick={() => onSelect(selected ? null : date)}
      title={names || undefined}
      aria-label={`${date}: ${n} event${n === 1 ? '' : 's'}${day?.competing ? ', competing' : ''}`}
      aria-pressed={selected}
      className={`relative h-8 rounded-sm border flex flex-col items-center justify-start pt-0.5 transition-colors overflow-hidden ${
        day?.competing
          ? 'border-red-400/80 bg-red-400/15'
          : selected
            ? 'border-secondary'
            : 'border-transparent hover:border-secondary/60'
      } ${weekend ? 'bg-bg-surface' : ''}`}
      style={soft && !day?.competing ? { boxShadow: `inset 0 -${Math.min(soft, 3) * 2}px 0 rgba(167,139,250,0.45)` } : undefined}
    >
      <span className={`text-[10px] leading-none ${n ? 'text-text-primary font-semibold' : 'text-text-muted'}`}>
        {toDate(date).getUTCDate()}
      </span>
      {n > 0 && (
        <span className="flex gap-px mt-0.5">
          {day.exact.slice(0, 3).map((entry) => (
            <span
              key={entry.application.id}
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: STATUS_COLORS[entry.application.status] || '#9ca3af' }}
            />
          ))}
          {n > 3 && <span className="text-[8px] leading-none text-text-muted">+</span>}
        </span>
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

const fill = (day) => {
  const n = day?.exact.length || 0
  if (day?.competing) return 'rgb(248 113 113)'
  if (n >= 3) return 'rgb(52 211 153)'
  if (n === 2) return 'rgba(52, 211, 153, 0.8)'
  if (n === 1) return 'rgba(52, 211, 153, 0.6)'
  if (day?.flexible) return `rgba(167, 139, 250, ${Math.min(0.1 + day.flexible * 0.06, 0.28)})`
  return null
}

/**
 * The whole season at a glance: a row per month, a small square per day.
 * Green squares are exact dates (darker = more events), red is a
 * competing weekend, violet is only flexible windows. Tap a day for detail.
 */
export default function MonthGrid({ weeks }) {
  const [selected, setSelected] = useState(null)
  const days = indexDays(weeks)
  const months = monthsFor(weeks)

  return (
    <div className="bg-bg-raised border border-border rounded-lg overflow-hidden max-w-3xl">
      <div className="p-2 sm:p-3 overflow-x-auto">
        <div
          className="grid gap-[2px] min-w-[18rem]"
          style={{ gridTemplateColumns: '2.25rem repeat(31, minmax(0, 1fr))' }}
        >
          <div />
          {Array.from({ length: 31 }, (_, i) => (
            <div key={i} className="text-[9px] text-center text-text-muted leading-none pb-0.5">
              {(i + 1) % 5 === 0 || i === 0 ? i + 1 : ''}
            </div>
          ))}
          {months.map((key) => {
            const first = toDate(`${key}-01`)
            const length = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate()
            return [
              <div key={`${key}-label`} className="text-[11px] text-text-muted leading-none self-center">
                {first.toLocaleDateString('en-US', { timeZone: 'UTC', month: 'short' })}
              </div>,
              ...Array.from({ length: 31 }, (_, i) => {
                const d = i + 1
                if (d > length) return <div key={`${key}-${d}`} />
                const date = `${key}-${String(d).padStart(2, '0')}`
                const day = days.get(date)
                const n = day?.exact.length || 0
                const weekend = [0, 6].includes(toDate(date).getUTCDay())
                const bg = fill(day)
                return (
                  <button
                    key={date}
                    type="button"
                    onClick={() => setSelected(selected === date ? null : date)}
                    aria-label={`${date}: ${n} event${n === 1 ? '' : 's'}${day?.competing ? ', competing' : ''}`}
                    aria-pressed={selected === date}
                    title={(day?.exact || []).map((e) => who(e.application)).join(', ') || undefined}
                    className={`aspect-square rounded-[2px] ${
                      selected === date ? 'ring-1 ring-secondary' : ''
                    } ${bg ? '' : weekend ? 'bg-text-muted/25' : 'bg-bg-surface'}`}
                    style={bg ? { backgroundColor: bg } : undefined}
                  />
                )
              }),
            ]
          })}
        </div>
      </div>
      {selected && <DayDetail date={selected} day={days.get(selected)} />}
    </div>
  )
}
