import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import { getApplications } from '@/api/explorerApplications'
import { STATUS_COLORS } from '@/components/explorer/statusColors'
import {
  BUSY_WEEKEND,
  COMPETING_MILES,
  buildCalendar,
  competingIds,
} from '@/components/explorer/calendarModel'

const STATUS_LABELS = {
  pending: 'Pending',
  pre_approved: 'Pre-approved',
  approved: 'Approved',
  rejected: 'Rejected',
}

const fmt = (iso, opts) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { timeZone: 'UTC', ...opts })

const who = (application) =>
  application.lgs_name || [application.first_name, application.last_name].filter(Boolean).join(' ')
  || application.discord_handle || `Application ${application.id}`

const where = (application) => [application.city, application.state].filter(Boolean).join(', ')

const RANK = { 1: '1st', 2: '2nd', 3: '3rd' }

function EntryChip({ entry, competing, flexible }) {
  const { application, row, rank } = entry
  const color = STATUS_COLORS[application.status] || '#9ca3af'
  const days = row.start_date === row.end_date
    ? fmt(row.start_date, { weekday: 'short' })
    : `${fmt(row.start_date, { month: 'short', day: 'numeric' })} – ${fmt(row.end_date, { month: 'short', day: 'numeric' })}`
  return (
    <li
      className={`inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5 max-w-full rounded px-2 py-1 text-xs border ${
        competing ? 'border-red-400/70 bg-red-400/10' : 'border-border bg-bg-surface'
      } ${flexible ? 'opacity-60 border-dashed' : ''} ${rank === 1 ? '' : 'text-text-muted'}`}
      title={`${STATUS_LABELS[application.status] || application.status} · ${RANK[rank] || `${rank}th`} choice${
        row.raw_text ? ` · “${row.raw_text}”` : ''}`}
    >
      <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} aria-hidden="true" />
      <span className="text-text-primary">{who(application)}</span>
      {where(application) && <span className="text-text-muted">{where(application)}</span>}
      <span className="text-text-muted">· {days}{rank !== 1 ? ` · ${RANK[rank] || rank} choice` : ''}</span>
    </li>
  )
}

function WeekRow({ week }) {
  const clashing = competingIds(week)
  const label = `${fmt(week.saturday, { month: 'short', day: 'numeric' })} – ${fmt(week.sunday, { day: 'numeric' })}`
  const empty = week.exact.length === 0 && week.flexible.length === 0
  return (
    <div
      className={`grid grid-cols-1 sm:grid-cols-[9rem_1fr] gap-2 py-2 px-3 border-b border-border/50 ${
        week.competing.length ? 'bg-red-400/5' : ''
      }`}
    >
      <div className="text-sm">
        <div className={empty ? 'text-text-muted' : 'text-text-primary'}>{label}</div>
        {week.competing.length > 0 && (
          <div className="text-xs text-red-400">
            Competing: {week.competing
              .map(({ miles }) => `${Math.round(miles)} mi apart`)
              .join(', ')}
          </div>
        )}
        {week.busy && <div className="text-xs text-amber-300">Busy: {week.exact.length} events</div>}
      </div>
      <div className="space-y-1.5">
        {week.exact.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {week.exact.map((entry) => (
              <EntryChip
                key={`${entry.application.id}-${entry.row.start_date}`}
                entry={entry}
                competing={clashing.has(entry.application.id)}
              />
            ))}
          </ul>
        )}
        {week.flexible.length > 0 && (
          <details className="text-xs text-text-muted">
            <summary className="cursor-pointer">
              {week.flexible.length} flexible ({week.flexible.map((e) => who(e.application)).slice(0, 3).join(', ')}
              {week.flexible.length > 3 ? '…' : ''})
            </summary>
            <ul className="flex flex-wrap gap-1.5 mt-1.5">
              {week.flexible.map((entry) => (
                <EntryChip key={`${entry.application.id}-f`} entry={entry} flexible />
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  )
}

/**
 * The 2027 Explorer calendar as applicants asked for it: one row per
 * weekend, coloured by review status, with competing events flagged.
 */
export default function ExplorerCalendar() {
  usePageTitle('Explorer Events Calendar')

  const [applications, setApplications] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showRejected, setShowRejected] = useState(false)
  const [approvedOnly, setApprovedOnly] = useState(false)
  const [firstChoiceOnly, setFirstChoiceOnly] = useState(false)
  const [problemsOnly, setProblemsOnly] = useState(false)

  useEffect(() => {
    getApplications()
      .then((data) => setApplications(data.applications || []))
      .catch((err) => setError(err.message || 'Failed to load applications'))
      .finally(() => setLoading(false))
  }, [])

  const included = applications.filter((a) =>
    approvedOnly ? a.status === 'approved' : showRejected || a.status !== 'rejected'
  )
  const weeks = useMemo(
    () => buildCalendar(included, { firstChoiceOnly }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [applications, showRejected, approvedOnly, firstChoiceOnly]
  )

  const competingWeeks = weeks.filter((w) => w.competing.length).length
  const busyWeeks = weeks.filter((w) => w.busy).length
  const withoutDates = included.filter((a) => !(a.dates || []).some((d) => d.start_date)).length
  const needCheck = included.filter((a) => a.dates_need_check).length
  const shownWeeks = problemsOnly ? weeks.filter((w) => w.competing.length || w.busy) : weeks

  const months = []
  shownWeeks.forEach((w) => {
    const key = w.saturday.slice(0, 7)
    if (!months.length || months.at(-1).key !== key) months.push({ key, weeks: [] })
    months.at(-1).weeks.push(w)
  })

  const toggle = 'inline-flex items-center gap-2 text-sm text-text-primary'

  return (
    <div className="max-w-content mx-auto px-4 py-8 space-y-6">
      <div className="space-y-1">
        <Link to="/admin/explorer-applications" className="text-xs text-text-muted hover:text-secondary">
          ← Explorer Applications
        </Link>
        <h1 className="text-2xl font-display text-secondary">Explorer Events Calendar</h1>
        <p className="text-sm text-text-muted">
          When applicants want to host, by weekend. Red means two events on the same weekend
          less than {COMPETING_MILES} miles apart.
        </p>
      </div>

      {error && (
        <div className="text-sm rounded p-3 border bg-accent-red/10 border-accent-red/30 text-accent-red">
          {error}
        </div>
      )}

      {!loading && (
        <section aria-label="Calendar summary" className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="bg-bg-raised border border-border rounded-lg p-4">
            <div className="text-xs text-text-muted">Competing weekends</div>
            <div className="text-3xl font-display text-red-400">{competingWeeks}</div>
          </div>
          <div className="bg-bg-raised border border-border rounded-lg p-4">
            <div className="text-xs text-text-muted">Busy weekends (over {BUSY_WEEKEND})</div>
            <div className="text-3xl font-display text-amber-300">{busyWeeks}</div>
          </div>
          <div className="bg-bg-raised border border-border rounded-lg p-4">
            <div className="text-xs text-text-muted">Dates need a check</div>
            <div className="text-3xl font-display text-violet-300">{needCheck}</div>
          </div>
          <div className="bg-bg-raised border border-border rounded-lg p-4">
            <div className="text-xs text-text-muted">No dates yet</div>
            <div className="text-3xl font-display text-text-primary">{withoutDates}</div>
          </div>
        </section>
      )}

      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <label className={toggle}>
          <input type="checkbox" checked={approvedOnly} onChange={(e) => setApprovedOnly(e.target.checked)} />
          Approved only
        </label>
        <label className={toggle}>
          <input
            type="checkbox"
            checked={showRejected}
            disabled={approvedOnly}
            onChange={(e) => setShowRejected(e.target.checked)}
          />
          Include rejected
        </label>
        <label className={toggle}>
          <input type="checkbox" checked={firstChoiceOnly} onChange={(e) => setFirstChoiceOnly(e.target.checked)} />
          First choices only
        </label>
        <label className={toggle}>
          <input type="checkbox" checked={problemsOnly} onChange={(e) => setProblemsOnly(e.target.checked)} />
          Only competing or busy weekends
        </label>
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-text-muted" aria-label="Legend">
        {Object.entries(STATUS_LABELS).map(([status, label]) => (
          <span key={status} className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: STATUS_COLORS[status] }} />
            {label}
          </span>
        ))}
        <span>Faded and dashed: flexible windows like “mid-June” or “summer”</span>
      </div>

      {loading ? (
        <p className="text-sm text-text-muted">Loading…</p>
      ) : months.length === 0 ? (
        <p className="text-sm text-text-muted">Nothing to show with these filters.</p>
      ) : (
        <div className="space-y-4">
          {months.map((month) => (
            <section key={month.key} className="bg-bg-raised border border-border rounded-lg overflow-hidden">
              <h2 className="px-3 py-2 text-sm font-semibold text-secondary border-b border-border">
                {fmt(`${month.key}-01`, { month: 'long', year: 'numeric' })}
              </h2>
              {month.weeks.map((week) => <WeekRow key={week.start} week={week} />)}
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
