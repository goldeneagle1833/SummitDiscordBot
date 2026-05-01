import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import Spinner from '@/components/ui/Spinner'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'

export default function DeckStats() {
  usePageTitle('Deck Stats')
  const { playerId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    get(`/api/players/${playerId}/deck-stats`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [playerId])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Deck Stats</h1>
      <pre className="text-sm text-text-muted bg-bg-surface p-4 rounded-soft overflow-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}
