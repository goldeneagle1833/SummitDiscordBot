import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPlayerPostseason } from '@/api/brackets'
import { Yurt } from '@/components/player/BracketMarks'

const GOLD_LABELS = new Set(['Champion', 'Finalist'])

const RESULT = {
  win: { text: 'W', label: 'Win', className: 'bg-secondary text-black' },
  loss: { text: 'L', label: 'Loss', className: 'bg-white/15 text-text-muted' },
  bye: { text: 'Bye', label: 'Bye', className: 'bg-bg-raised text-text-muted border border-border' },
  pending: { text: '...', label: 'Not played yet', className: 'bg-bg-raised text-text-muted border border-border' },
  waiting: { text: '...', label: 'Waiting for an opponent', className: 'bg-bg-raised text-text-muted border border-border' },
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

function RunStep({ game }) {
  const result = RESULT[game.result] || RESULT.pending
  return (
    <li className="flex items-center gap-3 rounded-lg bg-bg-raised/60 border border-border px-3 py-2.5 min-w-0">
      <span
        className={`shrink-0 min-w-8 h-8 px-1.5 rounded flex items-center justify-center text-xs font-bold ${result.className}`}
        aria-label={result.label}
        title={result.label}
      >
        {result.text}
      </span>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wider text-text-muted">{game.round_title}</div>
        {game.opponent_name ? (
          <div className="text-sm truncate">
            <span className="text-text-muted">vs </span>
            {game.opponent_user_id ? (
              <Link to={`/player/${game.opponent_user_id}`} className="font-semibold text-text-primary hover:text-secondary">
                {game.opponent_name}
              </Link>
            ) : (
              <span className="font-semibold text-text-primary">{game.opponent_name}</span>
            )}
            <span className="text-text-muted"> ({game.opponent_seed})</span>
            {game.opponent_avatar && <span className="text-text-muted"> · {game.opponent_avatar}</span>}
          </div>
        ) : (
          <div className="text-sm text-text-muted">{game.result === 'bye' ? 'Bye to the next round' : 'Opponent to be decided'}</div>
        )}
      </div>
    </li>
  )
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
    <section className="space-y-4">
      <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Postseason</h2>
      <ul className="space-y-4">
        {brackets.map((entry) => (
          <li key={entry.slug} className="bg-bg-surface border border-border rounded-xl p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  {entry.placement === 1 && <Yurt size={20} />}
                  <Link
                    to={`/brackets/${entry.slug}`}
                    className="text-lg font-bold text-text-primary hover:text-secondary transition-colors"
                  >
                    {entry.name}
                  </Link>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                      GOLD_LABELS.has(entry.label)
                        ? 'border-secondary/50 text-secondary'
                        : 'border-border text-text-muted'
                    }`}
                  >
                    {entry.label}
                  </span>
                </div>
                <p className="text-sm text-text-muted mt-1">
                  seed {entry.seed} of {entry.entrants} · {entry.wins}-{entry.losses}
                  {played(entry.played_at) ? ` · ${played(entry.played_at)}` : ''}
                  {entry.avatar ? ` · on ${entry.avatar}` : ''}
                </p>
              </div>
              <Link
                to={`/brackets/${entry.slug}`}
                className="shrink-0 h-10 px-4 inline-flex items-center rounded-lg border border-border bg-bg-raised text-sm font-semibold text-text-primary hover:border-secondary"
              >
                View bracket &rarr;
              </Link>
            </div>

            {entry.run?.length > 0 && (
              <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" aria-label={`${entry.name} run`}>
                {entry.run.map((game) => <RunStep key={game.match_no} game={game} />)}
              </ol>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
