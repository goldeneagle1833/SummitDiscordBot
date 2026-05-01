import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Elements() {
  usePageTitle('Elements')
  const [elements, setElements] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/elements')
      .then(setElements)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Elements</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {elements.map((el) => (
          <div
            key={el.name}
            className="bg-bg-surface border border-border rounded-soft p-4"
          >
            <h3 className="font-semibold text-lg mb-2">{el.name}</h3>
            {el.avatar_count != null && (
              <p className="text-sm text-text-muted">{el.avatar_count} avatars</p>
            )}
            {el.win_rate != null && (
              <p className="text-sm text-text-muted">
                Win Rate: {(el.win_rate * 100).toFixed(1)}%
              </p>
            )}
            {el.total_matches != null && (
              <p className="text-sm text-text-muted">{el.total_matches} matches</p>
            )}
          </div>
        ))}
      </div>
      {elements.length === 0 && (
        <p className="text-center text-text-muted py-8">No element data available.</p>
      )}
    </div>
  )
}
