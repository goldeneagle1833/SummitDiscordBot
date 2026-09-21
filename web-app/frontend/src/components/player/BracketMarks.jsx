import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { getBracketMarks } from '@/api/brackets'

/**
 * Postseason honours on a player's name: the name takes the colour of their
 * best finish, champions get one yurt per bracket won, and hovering the name
 * lists every placement.
 *
 * Every leaderboard row renders one of these, so the marks are fetched once
 * per page load and shared through a module-level cache.
 */

const YURT = '/static/images/favicon.png'

// Best finish -> name colour. Gold for a title, then down the podium.
export const FINISH_COLOURS = {
  Champion: 'text-yellow-300',
  Finalist: 'text-orange-300',
  'Top 4': 'text-sky-300',
  'Top 8': 'text-emerald-300',
  'Top cut': 'text-violet-300',
}

let cache = null
let inflight = null

function loadMarks() {
  if (cache) return Promise.resolve(cache)
  if (!inflight) {
    inflight = getBracketMarks()
      .then((res) => {
        cache = res?.marks || {}
        return cache
      })
      .catch(() => {
        // A leaderboard should never fail over its decorations.
        cache = {}
        return cache
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

/** Test hook: drop the cached marks (and optionally preload known ones). */
export function resetBracketMarksCache(preload = null) {
  cache = preload
  inflight = null
}

export function useBracketMarks(playerId) {
  const key = playerId == null ? '' : String(playerId)
  const [marks, setMarks] = useState(() => (cache && key ? cache[key] || null : null))

  useEffect(() => {
    if (!key) {
      setMarks(null)
      return undefined
    }
    let active = true
    loadMarks().then((all) => {
      if (active) setMarks(all[key] || null)
    })
    return () => {
      active = false
    }
  }, [key])

  return marks
}

export function Yurt({ size = 14, className = '' }) {
  return (
    <img
      src={YURT}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      className={`inline-block ${className}`}
      style={{ width: size, height: size }}
    />
  )
}

function PlacementsCard({ marks, anchor }) {
  const entries = marks.entries || []
  // Fixed to the viewport so a scrolling table cannot clip it.
  const style = {
    position: 'fixed',
    top: anchor.bottom + 6,
    left: Math.max(8, Math.min(anchor.left, window.innerWidth - 288)),
  }
  return createPortal(
    <div
      role="tooltip"
      style={style}
      className="z-50 w-72 max-w-[calc(100vw-16px)] rounded-lg border border-border bg-bg-surface shadow-xl p-3 text-xs pointer-events-none"
    >
      <p className="text-[10px] uppercase tracking-wide text-text-muted mb-2">Postseason</p>
      <ul className="space-y-1.5">
        {entries.map((entry) => (
          <li key={entry.slug} className="flex items-baseline justify-between gap-3">
            <span className="text-text-primary truncate">{entry.name}</span>
            <span
              className={`shrink-0 font-medium ${FINISH_COLOURS[entry.label] || FINISH_COLOURS['Top cut']}`}
            >
              {entry.label}
            </span>
          </li>
        ))}
      </ul>
    </div>,
    document.body,
  )
}

/**
 * Wrap a player's name (usually their profile link) in their postseason
 * colour. Players with no finishes get their name back untouched.
 */
export default function PostseasonName({ playerId, children, yurtSize = 14, className = '' }) {
  const marks = useBracketMarks(playerId)
  const ref = useRef(null)
  const [anchor, setAnchor] = useState(null)

  if (!marks || !marks.best_label) return children

  const show = () => {
    if (ref.current) setAnchor(ref.current.getBoundingClientRect())
  }
  const hide = () => setAnchor(null)
  const wins = marks.wins || 0
  const summary = (marks.entries || []).map((e) => `${e.label}: ${e.name}`).join('; ')

  return (
    <span
      ref={ref}
      data-finish={marks.best_label}
      className={`inline-flex items-center gap-1 ${FINISH_COLOURS[marks.best_label] || ''} ${className}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      aria-description={`Postseason: ${summary}`}
    >
      {children}
      {wins > 0 &&
        Array.from({ length: wins }, (_, i) => <Yurt key={i} size={yurtSize} />)}
      {anchor && <PlacementsCard marks={marks} anchor={anchor} />}
    </span>
  )
}
