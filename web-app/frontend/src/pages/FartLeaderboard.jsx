import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function FartLeaderboard() {
  usePageTitle('Fart Leaderboard')
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/fart-leaderboard')
      .then(setEntries)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Fart Leaderboard</h1>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 font-semibold text-text-muted">Rank</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Player</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Score</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, idx) => (
              <tr key={idx} className="border-b border-border/50 hover:bg-bg-surface/50">
                <td className="py-2 px-3 font-medium">{idx + 1}</td>
                <td className="py-2 px-3">{entry.display_name || entry.player_name || entry.name}</td>
                <td className="py-2 px-3 text-secondary font-medium">{entry.score ?? entry.points ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {entries.length === 0 && (
        <p className="text-center text-text-muted py-8">No fart leaderboard data available.</p>
      )}
    </div>
  )
}
