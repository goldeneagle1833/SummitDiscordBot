import { Link } from 'react-router-dom'
import CollapsibleSection from './CollapsibleSection'
import StatCard from './StatCard'

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
                </tr>
              </thead>
              <tbody>
                {limited.arena_runs.map((run) => (
                  <tr key={run.run_id} className="border-b border-border/50">
                    <td className="py-2 px-3">
                      <span className="text-accent-green">{run.wins}</span>
                      {' - '}
                      <span className="text-accent-red">{run.losses}</span>
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
