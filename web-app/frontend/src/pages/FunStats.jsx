import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function FunStats() {
  usePageTitle('Fun Stats')
  const [stats, setStats] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/fun-stats')
      .then(setStats)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Fun Stats</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {(Array.isArray(stats) ? stats : Object.entries(stats).map(([label, value]) => ({ label, value }))).map((stat, idx) => (
          <div
            key={idx}
            className="bg-bg-surface border border-border rounded-soft p-4 text-center"
          >
            <p className="text-sm text-text-muted mb-1">{stat.label}</p>
            <p className="text-2xl font-display text-secondary">{stat.value}</p>
          </div>
        ))}
      </div>
      {(Array.isArray(stats) ? stats : Object.keys(stats)).length === 0 && (
        <p className="text-center text-text-muted py-8">No fun stats available.</p>
      )}
    </div>
  )
}
