import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import Spinner from '@/components/ui/Spinner'
import { getLimitedLeaderboard } from '@/api/leaderboard'
import usePageTitle from '@/hooks/usePageTitle'

const SHOW_OPTIONS = [
  { value: 16, label: 'Top 16' },
  { value: 32, label: 'Top 32' },
  { value: 50, label: 'Top 50' },
  { value: Infinity, label: 'All Players' },
]

const RANK_MEDALS = ['\u{1F947}', '\u{1F948}', '\u{1F949}']

function StatBox({ label, value }) {
  return (
    <div className="bg-bg-surface border border-border rounded-soft p-3 text-center">
      <div className="text-lg font-display text-secondary">{value}</div>
      <div className="text-xs text-text-muted">{label}</div>
    </div>
  )
}

function TrophyRuns({ runs }) {
  if (!runs?.length) return null

  return (
    <section className="mb-8">
      <h2 className="text-xl font-display text-secondary mb-1">Trophy Runs (4-0)</h2>
      <p className="text-sm text-text-muted mb-4">Perfect arena runs</p>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-border">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Player</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">Record</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">Deck</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase hidden sm:table-cell">Starting ELO</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {runs.map((run) => (
              <tr key={run.run_id} className="hover:bg-bg-elevated transition-colors">
                <td className="px-3 py-2">
                  <Link
                    to={`/player/${run.user_id}`}
                    className="text-sm font-medium hover:text-primary transition-colors"
                  >
                    {run.user_display_name}
                  </Link>
                </td>
                <td className="px-3 py-2 text-sm text-center">
                  <span className="text-accent-green">{run.wins}</span>
                  {'-'}
                  <span className="text-accent-red">{run.losses}</span>
                </td>
                <td className="px-3 py-2 text-center">
                  {run.deck_url ? (
                    <a
                      href={run.deck_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-secondary hover:underline text-xs"
                    >
                      View Deck
                    </a>
                  ) : '-'}
                </td>
                <td className="px-3 py-2 text-sm text-right text-text-muted hidden sm:table-cell">
                  {run.starting_elo}
                </td>
                <td className="px-3 py-2 text-sm text-right text-text-muted">
                  {run.completed_at ? new Date(run.completed_at).toLocaleDateString() : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function LimitedLeaderboardTable({ data }) {
  const [showCount, setShowCount] = useState(16)
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
              <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider hidden sm:table-cell">ELO</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider hidden sm:table-cell">W/L</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-text-muted uppercase tracking-wider">Win %</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {visible.map((entry, index) => {
              const rankDisplay = index < 3 ? RANK_MEDALS[index] : `#${index + 1}`
              const totalGames = (entry.wins || 0) + (entry.losses || 0)
              const winPct = totalGames > 0 ? ((entry.wins / totalGames) * 100).toFixed(1) : '0.0'

              return (
                <tr key={entry.id} className="hover:bg-bg-elevated transition-colors">
                  <td className="px-3 py-2 text-sm text-text-muted">{rankDisplay}</td>
                  <td className="px-3 py-2">
                    <Link
                      to={`/player/${entry.id}`}
                      className="text-sm font-medium hover:text-primary transition-colors"
                    >
                      {entry.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-sm text-right hidden sm:table-cell">{entry.elo}</td>
                  <td className="px-3 py-2 text-sm text-right hidden sm:table-cell">
                    <span className="text-accent-green">{entry.wins || 0}</span>
                    {'-'}
                    <span className="text-accent-red">{entry.losses || 0}</span>
                  </td>
                  <td className="px-3 py-2 text-sm text-right">{winPct}%</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function LimitedLeaderboard() {
  usePageTitle('Limited Leaderboard')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getLimitedLeaderboard()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />

  if (!data) {
    return (
      <div className="text-center py-20">
        <h1 className="text-2xl font-display text-secondary mb-2">Limited Leaderboard</h1>
        <p className="text-text-muted">Limited leaderboard is not currently available.</p>
      </div>
    )
  }

  const leaderboard = data.leaderboard || data
  const trophyRuns = data.trophy_runs || []
  const stats = data.stats || {}

  return (
    <div>
      <section className="text-center mb-8">
        <h1 className="text-2xl font-display text-secondary">Limited Leaderboard</h1>
        <p className="text-sm text-text-muted">Arena draft rankings - lifetime ELO</p>
      </section>

      {/* Stats Overview */}
      {stats.unique_players > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          <StatBox label="Players" value={stats.unique_players} />
          <StatBox label="Runs Completed" value={stats.total_runs} />
          <StatBox label="Matches Played" value={stats.total_matches} />
          <StatBox label="Trophy Runs (4-0)" value={stats.trophy_runs} />
        </div>
      )}

      {/* Leaderboard */}
      <section className="mb-8">
        <h2 className="text-xl font-display text-secondary mb-1">Lifetime Limited ELO</h2>
        <p className="text-sm text-text-muted mb-4">Cumulative limited format rankings</p>
        <LimitedLeaderboardTable data={Array.isArray(leaderboard) ? leaderboard : []} />
      </section>

      {/* Trophy Runs */}
      <TrophyRuns runs={trophyRuns} />
    </div>
  )
}
