import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPaperFinishes } from '@/api/paperFinishes'

/**
 * Paper tournament finishes: the player's results in the top cuts on the
 * Top 8 page, matched to their profile by name ("Winner · SCG Con Atlanta").
 *
 * Fetched once per page load and shared through a module-level cache, like
 * the season avatar honours.
 */

const FINISH_COLOURS = {
  Winner: 'text-secondary',
  Finalist: 'text-slate-200',
  'Top 4': 'text-amber-600',
}

let cache = null
let inflight = null

function loadFinishes() {
  if (cache) return Promise.resolve(cache)
  if (!inflight) {
    inflight = getPaperFinishes()
      .then((res) => {
        cache = res?.finishes || {}
        return cache
      })
      .catch(() => {
        // A profile should never fail over its decorations.
        cache = {}
        return cache
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

/** Test hook: drop the cached finishes (and optionally preload known ones). */
export function resetPaperFinishesCache(preload = null) {
  cache = preload
  inflight = null
}

const bareId = (id) => (id.startsWith('google_') ? id.slice(7) : id)

/** One player's finishes, best first ([] when they have none). */
export function usePaperFinishes(playerId) {
  const key = playerId == null ? '' : bareId(String(playerId))
  const [finishes, setFinishes] = useState(() => (cache && key ? cache[key] || [] : []))

  useEffect(() => {
    if (!key) {
      setFinishes([])
      return undefined
    }
    let active = true
    loadFinishes().then((all) => {
      if (active) setFinishes(all[key] || [])
    })
    return () => {
      active = false
    }
  }, [key])

  return finishes
}

function Trophy({ label, size = 15 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      strokeLinecap="round"
      className={FINISH_COLOURS[label] || 'text-text-muted'}
      aria-hidden="true"
    >
      <path d="M7 4 h10 v5 a5 5 0 0 1 -10 0 Z" />
      <path d="M7 6 H4 a3 3 0 0 0 3 4" />
      <path d="M17 6 h3 a3 3 0 0 1 -3 4" />
      <path d="M12 14 v4" />
      <path d="M8 21 h8" />
    </svg>
  )
}

/**
 * The hero card's paper finishes: one chip per event, best first, each
 * opening that event's Top 8 page. Long event names are cut short on the
 * chip; hovering shows the full title.
 */
export function PaperFinishChips({ finishes = [] }) {
  if (!finishes.length) return null
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Paper tournament finishes">
      {finishes.map((f) => (
        <li key={f.folder} className="min-w-0 max-w-full">
          <Link
            to={`/top-8/${encodeURIComponent(f.folder)}`}
            title={f.title}
            className="flex items-center gap-1.5 sm:gap-2 max-w-full px-2.5 sm:px-3 py-1 rounded-full bg-bg-raised border border-secondary/40 text-xs sm:text-sm hover:border-secondary"
          >
            <Trophy label={f.label} size={14} />
            <strong className={`whitespace-nowrap ${FINISH_COLOURS[f.label] || 'text-text-primary'}`}>{f.label}</strong>
            <span className="text-text-muted truncate">{f.event}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** The Postseason tab's list of paper finishes, best first. */
export function PaperFinishesSection({ finishes = [] }) {
  if (!finishes.length) return null
  return (
    <section className="space-y-4">
      <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Paper tournament finishes</h2>
      <ul className="bg-bg-surface border border-border rounded-xl divide-y divide-border">
        {finishes.map((f) => (
          <li key={f.folder} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3">
            <span className="inline-flex items-center gap-2 min-w-[7.5rem]">
              <Trophy label={f.label} />
              <strong className={FINISH_COLOURS[f.label] || 'text-text-primary'}>{f.label}</strong>
            </span>
            <Link
              to={`/top-8/${encodeURIComponent(f.folder)}`}
              className="font-semibold text-text-primary hover:text-secondary flex-1 min-w-[12rem]"
            >
              {f.event}
            </Link>
            <span className="text-sm text-text-muted">
              {[f.avatar, f.event_date_display].filter(Boolean).join(' · ')}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-text-muted">
        From the events on the Top 8 page, matched to this profile by name. Wrong name, or a finish missing? Let an admin know.
      </p>
    </section>
  )
}
