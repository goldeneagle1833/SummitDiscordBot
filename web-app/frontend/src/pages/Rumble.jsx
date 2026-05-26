import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Rumble() {
  usePageTitle('Rumble')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/rumble')
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  const { standings, matches, total_matches } = data

  return (
    <div className="space-y-6">
      <div className="text-center py-6">
        <h1 className="text-3xl font-display text-secondary">Rumble</h1>
        <p className="text-text-muted mt-1">
          {total_matches} match{total_matches !== 1 ? 'es' : ''} played
        </p>
      </div>

      {/* Standings */}
      {standings?.length > 0 && (
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-base font-semibold text-text-primary mb-3">Player Records</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-1.5 px-2 text-text-muted font-semibold w-8">#</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Player</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">W</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">L</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Games</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Win %</th>
                </tr>
              </thead>
              <tbody>
                {standings.map((p, i) => {
                  const total = p.wins + p.losses
                  const pct = total > 0 ? Math.round((p.wins / total) * 100) : 0
                  return (
                    <tr key={p.user_id} className="border-b border-border/50">
                      <td className="py-1.5 px-2 text-text-muted">{i + 1}</td>
                      <td className="py-1.5 px-2 font-medium">{p.display_name || 'Unknown'}</td>
                      <td className="py-1.5 px-2 text-accent-green">{p.wins}</td>
                      <td className="py-1.5 px-2 text-accent-red">{p.losses}</td>
                      <td className="py-1.5 px-2">{total}</td>
                      <td className="py-1.5 px-2">{pct}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent Matches */}
      {matches?.length > 0 && (
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-base font-semibold text-text-primary mb-3">Recent Matches</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Winner</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Loser</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Time</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Date</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m) => (
                  <tr key={m.match_id} className="border-b border-border/50">
                    <td className="py-1.5 px-2 text-accent-green">{m.winner}</td>
                    <td className="py-1.5 px-2 text-accent-red">{m.loser}</td>
                    <td className="py-1.5 px-2 text-text-muted">
                      {m.match_time > 0 ? `${m.match_time} min` : '-'}
                    </td>
                    <td className="py-1.5 px-2 text-text-muted">
                      {m.timestamp ? new Date(m.timestamp).toLocaleDateString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!standings?.length && !matches?.length && (
        <p className="text-center text-text-muted py-8">No rumble matches yet.</p>
      )}
    </div>
  )
}
