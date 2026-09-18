import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getBracketMarks } from '@/api/brackets'

/**
 * Postseason honours beside a player's name: one yurt per bracket won, or a
 * tag for their best finish if they have not won one.
 *
 * Every leaderboard row renders one of these, so the marks are fetched once
 * per page load and shared through a module-level cache.
 */

const YURT = '/static/images/favicon.png'

const TAG_STYLES = {
  Finalist: 'text-amber-300 border-amber-300/40',
  'Top 4': 'text-sky-300 border-sky-300/40',
  'Top 8': 'text-text-muted border-border',
  'Top cut': 'text-text-muted border-border',
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

export default function BracketMarks({ playerId, size = 14, linkTo = true, className = '' }) {
  const marks = useBracketMarks(playerId)
  if (!marks) return null

  const wins = marks.wins || 0
  const won = (marks.entries || []).filter((e) => e.placement === 1).map((e) => e.name)

  let body = null
  if (wins > 0) {
    const tooltip =
      wins === 1 ? `Won ${won[0] || 'a bracket'}` : `${wins}x bracket winner: ${won.join(', ')}`
    body = (
      <span
        className={`inline-flex items-center gap-0.5 align-middle ${className}`}
        title={tooltip}
        aria-label={tooltip}
        role="img"
      >
        {Array.from({ length: wins }, (_, i) => (
          <Yurt key={i} size={size} />
        ))}
      </span>
    )
  } else if (marks.best_label) {
    const deepest = (marks.entries || []).find((e) => e.label === marks.best_label)
    body = (
      <span
        className={`inline-block align-middle px-1.5 py-px rounded border text-[10px] uppercase tracking-wide ${
          TAG_STYLES[marks.best_label] || TAG_STYLES['Top cut']
        } ${className}`}
        title={deepest ? `${marks.best_label} — ${deepest.name}` : marks.best_label}
      >
        {marks.best_label}
      </span>
    )
  }

  if (!body) return null
  if (!linkTo) return body

  return (
    <Link
      to={`/brackets`}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex hover:opacity-80 transition-opacity"
    >
      {body}
    </Link>
  )
}
