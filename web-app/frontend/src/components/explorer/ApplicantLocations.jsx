import { lazy, Suspense, useState } from 'react'
import { STATUS_COLORS } from './statusColors'

// Leaflet is heavy and needs real layout, so the map loads on its own.
const ApplicationsMap = lazy(() => import('./ApplicationsMap'))

const OPEN_KEY = 'explorer-applicant-locations-open'

const STATUS_LEGEND = [
  { value: 'pending', label: 'Pending' },
  { value: 'pre_approved', label: 'Pre-approved' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

const US_NAMES = new Set(['', 'us', 'usa', 'u.s.', 'u.s.a.', 'united states', 'united states of america', 'america'])

/**
 * The region an application counts toward: its state for US applicants,
 * its country for everyone else.
 */
export function regionOf(application) {
  const country = (application.country || '').trim()
  if (US_NAMES.has(country.toLowerCase())) {
    const state = (application.state || '').trim()
    return state ? (state.length <= 3 ? state.toUpperCase() : state) : 'USA (no state)'
  }
  return country
}

function hasPin(application) {
  return typeof application.latitude === 'number' && typeof application.longitude === 'number'
}

function readOpen() {
  try {
    return localStorage.getItem(OPEN_KEY) !== '0'
  } catch {
    return true
  }
}

/**
 * Where this season's applicants want to run events: a pin map of every
 * submitted application (admin-added candidates are left out) plus a count
 * per state or country. Shows every application whatever the board filters
 * are set to, so it always reads as the full regional picture.
 */
export default function ApplicantLocations({ applications, onSelect }) {
  const [open, setOpen] = useState(readOpen)

  const submitted = applications.filter((a) => a.source !== 'admin_added')
  if (submitted.length === 0) return null

  const pinned = submitted.filter(hasPin)
  const unpinned = submitted.length - pinned.length

  const counts = new Map()
  submitted.forEach((a) => {
    const region = regionOf(a)
    counts.set(region, (counts.get(region) || 0) + 1)
  })
  const regions = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))

  const toggle = () => {
    const next = !open
    setOpen(next)
    try {
      localStorage.setItem(OPEN_KEY, next ? '1' : '0')
    } catch {
      // Storage blocked: the panel just won't remember.
    }
  }

  return (
    <section className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="flex items-center gap-2 text-left"
        >
          <span className={`text-xs text-text-muted transition-transform ${open ? 'rotate-90' : ''}`}>▶</span>
          <h2 className="text-lg font-display text-secondary">Applicant locations</h2>
        </button>
        <p className="text-xs text-text-muted">
          {submitted.length} application{submitted.length === 1 ? '' : 's'} from{' '}
          {regions.length} region{regions.length === 1 ? '' : 's'}
          {unpinned > 0 && ` · ${unpinned} without a pin yet`}
        </p>
      </div>

      {open && (
        <>
          <Suspense fallback={<div className="h-80 rounded-lg border border-border bg-bg-surface" />}>
            <ApplicationsMap applications={pinned} onSelect={onSelect} height="h-80 sm:h-[26rem]" fitToPoints />
          </Suspense>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1" aria-label="Pin colours">
            {STATUS_LEGEND.map((s) => (
              <span key={s.value} className="flex items-center gap-1 text-xs text-text-muted">
                <span
                  className="inline-block w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: STATUS_COLORS[s.value] }}
                />
                {s.label}
              </span>
            ))}
          </div>

          <div>
            <h3 className="text-xs uppercase tracking-wide text-text-muted mb-1.5">
              Applications by state / country
            </h3>
            <ul className="flex flex-wrap gap-1.5">
              {regions.map(([region, count]) => (
                <li
                  key={region}
                  className="text-xs px-2 py-0.5 rounded border border-border bg-bg-surface text-text-primary"
                >
                  {region} <span className="text-secondary font-semibold">{count}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  )
}
