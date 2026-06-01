import { useState, useEffect } from 'react'
import Spinner from '@/components/ui/Spinner'
import { getLimitedLeaderboard } from '@/api/leaderboard'
import { StatBox, TrophyRuns, LimitedLeaderboardTable } from '@/components/leaderboard/LimitedLeaderboardContent'
import usePageTitle from '@/hooks/usePageTitle'

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
