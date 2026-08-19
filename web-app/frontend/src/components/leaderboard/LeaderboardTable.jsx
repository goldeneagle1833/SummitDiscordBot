import { useState } from 'react'
import { Link } from 'react-router-dom'

const SHOW_OPTIONS = [
  { value: 16, label: 'Top 16' },
  { value: 32, label: 'Top 32' },
  { value: 50, label: 'Top 50' },
  { value: 100, label: 'Top 100' },
  { value: Infinity, label: 'All Players' },
]

const RANK_MEDALS = ['\u{1F947}', '\u{1F948}', '\u{1F949}']

export default function LeaderboardTable({ data = [], columns = 'lifetime' }) {
  const [showCount, setShowCount] = useState(16)
  const hasAvatars = columns === 'event' && data.some((entry) => entry.avatar)

  const visible = data.slice(0, showCount === Infinity ? data.length : showCount)

  if (!data.length) {
    return <p className="text-text-muted text-center py-8">No data available.</p>
  }

  return (
    <div>
      <div className="flex justify-center mb-4">
        <label className="text-sm text-text-muted mr-2 self-center">Show:</label>
        <select
          value={showCount}
          onChange={(e) => setShowCount(e.target.value === 'Infinity' ? Infinity : Number(e.target.value))}
          className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
        >
          {SHOW_OPTIONS.map(({ value, label }) => (
            <option key={label} value={value}>{label}</option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-border">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase tracking-wider w-12">#</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase tracking-wider">Player</th>
              {hasAvatars && (
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase tracking-wider">Avatar</th>
              )}
              {columns === 'lifetime' && (
                <>
                  <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider hidden sm:table-cell">ELO</th>
                  <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase tracking-wider hidden md:table-cell">Mode</th>
                  <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider hidden sm:table-cell">W/L</th>
                  <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider">Win %</th>
                </>
              )}
              {columns === 'event' && (
                <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider">Event ELO</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {visible.map((entry, index) => {
              const rankDisplay = index < 3 ? RANK_MEDALS[index] : `#${index + 1}`
              const totalGames = (entry.wins || 0) + (entry.losses || 0)
              const winPct = totalGames > 0 ? ((entry.wins / totalGames) * 100).toFixed(1) : '0.0'
              const playerId = entry.id || entry.user_id

              return (
                <tr key={`${playerId}:${entry.avatar || 'player'}`} className="hover:bg-bg-elevated transition-colors">
                  <td className="px-3 py-2 text-sm text-text-muted">{rankDisplay}</td>
                  <td className="px-3 py-2">
                    <Link
                      to={`/player/${playerId}`}
                      className="text-sm font-medium hover:text-primary transition-colors"
                    >
                      {entry.name || entry.display_name}
                    </Link>
                  </td>
                  {hasAvatars && (
                    <td className="px-3 py-2 text-sm text-text-muted">{entry.avatar || '—'}</td>
                  )}
                  {columns === 'lifetime' && (
                    <>
                      <td className="px-3 py-2 text-sm text-right hidden sm:table-cell">{entry.elo}</td>
                      <td className="px-3 py-2 text-sm text-center hidden md:table-cell">
                        {entry.primary_mode === 'Paper' ? (
                          <span className="inline-block px-2 py-0.5 text-xs rounded bg-amber-900/30 text-amber-400" title="Paper games ELO is higher">Paper</span>
                        ) : (
                          <span className="inline-block px-2 py-0.5 text-xs rounded bg-blue-900/30 text-blue-400" title="Online games ELO is higher">Online</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-sm text-right hidden sm:table-cell">
                        <span className="text-accent-green">{entry.wins || 0}</span>
                        {'-'}
                        <span className="text-accent-red">{entry.losses || 0}</span>
                      </td>
                      <td className="px-3 py-2 text-sm text-right">{winPct}%</td>
                    </>
                  )}
                  {columns === 'event' && (
                    <td className="px-3 py-2 text-sm text-right">{entry.event_elo}</td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
