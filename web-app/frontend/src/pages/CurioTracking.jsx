import { useState, useEffect } from 'react'
import { getCurioEntries } from '@/api/curios'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function CurioTracking() {
  usePageTitle('Curio Tracking')
  const [entries, setEntries] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getCurioEntries()
      .then(setEntries)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = entries.filter((entry) =>
    (entry.name || '').toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Curio Tracking</h1>
      <input
        type="text"
        placeholder="Filter curios..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full sm:w-80 mb-4 px-3 py-2 bg-bg-surface border border-border rounded-soft text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
      />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 font-semibold text-text-muted">Name</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Set</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Rarity</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Count</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((entry, idx) => (
              <tr key={idx} className="border-b border-border/50 hover:bg-bg-surface/50">
                <td className="py-2 px-3">{entry.name}</td>
                <td className="py-2 px-3 text-text-muted">{entry.set || '-'}</td>
                <td className="py-2 px-3 text-text-muted">{entry.rarity || '-'}</td>
                <td className="py-2 px-3 text-text-muted">{entry.count ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <p className="text-center text-text-muted py-8">No curio entries found.</p>
      )}
    </div>
  )
}
