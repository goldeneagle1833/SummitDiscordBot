import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPlayerPostseason } from '@/api/brackets'
import { Yurt } from '@/components/player/BracketMarks'

const LABEL_STYLES = {
  Champion: 'text-amber-400',
  Finalist: 'text-amber-300',
  'Top 4': 'text-sky-300',
  'Top 8': 'text-text-muted',
  'Top cut': 'text-text-muted',
  'Still in': 'text-accent-green',
}

function played(value) {
  if (!value) return null
  const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  const date = parts
    ? new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]))
    : new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short' })
}

/** A player's bracket runs. Hidden entirely for players who have never been in one. */
export default function PostseasonSection({ playerId }) {
  const [brackets, setBrackets] = useState(null)

  useEffect(() => {
    if (!playerId) return undefined
    let active = true
    getPlayerPostseason(playerId)
      .then((res) => active && setBrackets(res.brackets || []))
      .catch(() => active && setBrackets([]))
    return () => {
      active = false
    }
  }, [playerId])

  if (!brackets?.length) return null

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5">
      <h2 className="font-display mb-3">Postseason</h2>
      <ul className="space-y-2">
        {brackets.map((entry) => (
          <li
            key={entry.slug}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
          >
            {entry.placement === 1 && <Yurt size={16} />}
            <Link
              to={`/brackets/${entry.slug}`}
              className="font-medium hover:text-primary transition-colors"
            >
              {entry.name}
            </Link>
            <span className={LABEL_STYLES[entry.label] || 'text-text-muted'}>{entry.label}</span>
            <span className="text-text-muted text-xs">
              seed {entry.seed} of {entry.entrants} · {entry.wins}-{entry.losses}
              {played(entry.played_at) ? ` · ${played(entry.played_at)}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
