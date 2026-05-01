import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getEvents } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Stats() {
  usePageTitle('Stats')
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
      <h1 className="text-2xl font-display text-secondary mb-4">Event Stats</h1>
      <div className="space-y-2">
        {events.map((event) => (
          <Link
            key={event.folder}
            to={`/stats/${event.folder}`}
            className="block bg-bg-surface border border-border rounded-soft p-3 hover:border-primary/50 transition-colors"
          >
            <span className="font-medium">{event.display_name || event.folder}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
