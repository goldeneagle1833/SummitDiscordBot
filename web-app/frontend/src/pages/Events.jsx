import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getEvents } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Events() {
  usePageTitle('Events')
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getEvents()
      .then(setEvents)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Events & Decks</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {events.map((event) => (
          <Link
            key={event.folder}
            to={`/top-8/${event.folder}`}
            className="bg-bg-surface border border-border rounded-soft p-4 hover:border-primary/50 transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold truncate">{event.display_name || event.folder}</h3>
              <span className="text-secondary text-sm flex-shrink-0">
                {'★'.repeat(event.star_rating || 1)}
              </span>
            </div>
            <p className="text-sm text-text-muted">
              {event.top8?.length || 0} top 8 decks
              {event.all_decks?.length ? ` · ${event.all_decks.length} total` : ''}
            </p>
          </Link>
        ))}
      </div>
    </div>
  )
}
