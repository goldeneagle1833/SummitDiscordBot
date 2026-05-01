import { useState, useEffect, lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { getEvent } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const DeckViewer = lazy(() => import('@/components/deck/DeckViewer'))

export default function EventDetail() {
  usePageTitle('Event Detail')
  const { folder } = useParams()
  const [event, setEvent] = useState(null)
  const [expandedDeck, setExpandedDeck] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getEvent(folder)
      .then((data) => {
        setEvent(data)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [folder])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!event) return null

  const decks = event.top8 || []

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-1">
        {event.display_name || folder}
      </h1>
      {event.star_rating && (
        <p className="text-secondary mb-4">{'★'.repeat(event.star_rating)}</p>
      )}

      <div className="space-y-3">
        {decks.map((deck, idx) => (
          <div key={idx} className="bg-bg-surface border border-border rounded-soft">
            <button
              className="w-full flex items-center justify-between p-4 text-left hover:bg-bg-elevated transition-colors"
              onClick={() => setExpandedDeck(expandedDeck === idx ? null : idx)}
            >
              <div className="flex items-center gap-3">
                {deck.placement && (
                  <span className="text-secondary font-bold">#{deck.placement}</span>
                )}
                <span className="font-medium">{deck.player_name}</span>
              </div>
              <span className="text-text-muted text-sm">
                {expandedDeck === idx ? '▲' : '▼'}
              </span>
            </button>
            {expandedDeck === idx && deck.deck_data && (
              <div className="p-4 border-t border-border">
                <Suspense fallback={<Spinner />}>
                  <DeckViewer deck={deck.deck_data} />
                </Suspense>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
