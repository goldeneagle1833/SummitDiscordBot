import { useState } from 'react'
import { Link } from 'react-router-dom'
import CollapsibleSection from './CollapsibleSection'
import StatCard from './StatCard'
import { getRunMatchups } from '@/api/leaderboard'

function RunMatchups({ runId, userId }) {
  const [matchups, setMatchups] = useState(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)

  const toggle = () => {
    if (!open && matchups === null) {
      setLoading(true)
      getRunMatchups(runId)
        .then((data) => setMatchups(data.matchups || []))
        .catch(() => setMatchups([]))
        .finally(() => setLoading(false))
    }
    setOpen(!open)
  }

  return (
    <div>
      <button
        onClick={toggle}
        className="text-xs text-secondary hover:underline"
      >
        {open ? 'Hide' : 'Matchups'}
      </button>
      {open && (
        <div className="mt-2">
          {loading && <span className="text-xs text-text-muted">Loading...</span>}
          {matchups && matchups.length === 0 && (
            <span className="text-xs text-text-muted">No matches recorded</span>
          )}
          {matchups && matchups.length > 0 && (
            <div className="space-y-1">
              {matchups.map((m) => {
                const isWin = String(m.winner_id) === String(userId)
                const oppName = isWin ? m.loser_name : m.winner_name
                const oppId = isWin ? m.loser_id : m.winner_id
                const eloChange = isWin ? m.winner_elo_change : m.loser_elo_change

                return (
                  <div key={m.match_id} className="flex items-center gap-2 text-xs">
                    <span className={isWin ? 'text-accent-green font-medium' : 'text-accent-red font-medium'}>
                      {isWin ? 'W' : 'L'}
                    </span>
                    <span className="text-text-muted">vs</span>
                    <Link to={`/player/${oppId}`} className="text-secondary hover:underline">
                      {oppName}
                    </Link>
                    <span className={isWin ? 'text-accent-green' : 'text-accent-red'}>
                      ({isWin ? '+' : ''}{eloChange})
                    </span>
                    {m.opponent_deck_url && (
                      <a
                        href={m.opponent_deck_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-secondary/70 hover:text-secondary hover:underline"
                      >
                        [deck]
                      </a>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function LimitedArena({ limited, playerId, open, onToggle }) {
  if (!limited?.has_data) return null

  return (
    <CollapsibleSection title="Limited Arena" open={open} onToggle={onToggle}>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        <StatCard label="Limited ELO" value={limited.elo ?? '-'} />
        <StatCard label="Wins" value={limited.total_wins ?? '-'} />
        <StatCard label="Losses" value={limited.total_losses ?? '-'} />
        <StatCard label="Win Rate" value={limited.win_rate != null ? `${limited.win_rate}%` : '-'} />
        <StatCard label="Arena Runs" value={limited.arena_runs?.length ?? 0} />
      </div>

      {limited.arena_runs?.length > 0 && (
        <>
          <h4 className="text-sm font-semibold text-text-muted mb-2">Arena Runs</h4>
          <div className="overflow-x-auto mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-2 px-3 text-text-muted font-semibold">Record</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Status</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Deck</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Starting ELO</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Details</th>
                </tr>
              </thead>
              <tbody>
                {limited.arena_runs.map((run) => (
                  <tr key={run.run_id} className="border-b border-border/50 align-top">
                    <td className="py-2 px-3">
                      <span className="text-accent-green">{run.wins}</span>
                      {' - '}
                      <span className="text-accent-red">{run.losses}</span>
                      {run.wins === 4 && run.losses === 0 && (
                        <span className="ml-1" title="Perfect run!">&#127942;</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-text-muted capitalize">{run.status}</td>
                    <td className="py-2 px-3">
                      {run.deck_url ? (
                        <a href={run.deck_url} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline text-xs">
                          View
                        </a>
                      ) : '-'}
                    </td>
                    <td className="py-2 px-3 text-text-muted">{run.starting_elo}</td>
                    <td className="py-2 px-3 text-text-muted">{run.created_at ?? '-'}</td>
                    <td className="py-2 px-3">
                      {run.status !== 'active' && (
                        <RunMatchups runId={run.run_id} userId={playerId} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {limited.recent_matches?.length > 0 && (
        <>
          <h4 className="text-sm font-semibold text-text-muted mb-2">Recent Limited Matches</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-2 px-3 text-text-muted font-semibold">Result</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Opponent</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">ELO</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Time</th>
                  <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
                </tr>
              </thead>
              <tbody>
                {limited.recent_matches.map((m) => {
                  const isWin = m.winner_id === playerId
                  return (
                    <tr key={m.match_id} className="border-b border-border/50">
                      <td className="py-2 px-3">
                        <span className={isWin ? 'text-accent-green' : 'text-accent-red'}>{isWin ? 'Win' : 'Loss'}</span>
                      </td>
                      <td className="py-2 px-3">
                        <Link to={`/player/${isWin ? m.loser_id : m.winner_id}`} className="text-secondary hover:underline">
                          {isWin ? m.loser_name : m.winner_name}
                        </Link>
                      </td>
                      <td className={`py-2 px-3 ${isWin ? 'text-accent-green' : 'text-accent-red'}`}>
                        {isWin ? `+${m.winner_elo_change}` : m.loser_elo_change}
                      </td>
                      <td className="py-2 px-3 text-text-muted">{m.match_time ? `${m.match_time} min` : '-'}</td>
                      <td className="py-2 px-3 text-text-muted">{m.timestamp ? new Date(m.timestamp).toLocaleDateString() : '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </CollapsibleSection>
  )
}
