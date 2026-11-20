import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Spinner from '@/components/ui/Spinner'
import Avatar from '@/components/ui/Avatar'
import usePageTitle from '@/hooks/usePageTitle'
import HallMap from '@/components/finder/HallMap'
import { closedMessage, getFinderPerson, timeAgo } from '@/api/eventFinder'

const REFRESH_MS = 60 * 1000

// One person's spot at an event, opened from their link or QR code.
export default function FindPerson() {
  const { token } = useParams()
  const [person, setPerson] = useState(null)
  const [loading, setLoading] = useState(true)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState(null)
  const [, setTick] = useState(0)
  usePageTitle(person ? `Find ${person.username}` : 'Find a player')

  const load = useCallback(() => {
    return getFinderPerson(token)
      .then((d) => {
        setPerson(d)
        setError(null)
      })
      .catch((err) => {
        if (err.status === 404) setMissing(true)
        else setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [token])

  useEffect(() => {
    load()
    // Refresh while the page is on screen; skip hidden tabs
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load()
      setTick((t) => t + 1)
    }, REFRESH_MS)
    const onVisible = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load])

  if (loading) return <Spinner className="py-20" />
  if (missing) {
    return (
      <div className="max-w-lg mx-auto text-center py-16 px-4">
        <h1 className="text-2xl font-display text-secondary mb-2">This link isn&apos;t working</h1>
        <p className="text-text-muted mb-8">It may be an old link. Ask the person for their new one.</p>
        <Link to="/find" className="text-primary hover:underline">See who&apos;s sharing at the event</Link>
      </div>
    )
  }
  if (error && !person) return <p className="text-center text-accent-red py-8">{error}</p>

  const p = person
  const hasPin = p.live && p.x != null && p.y != null

  return (
    <div className="max-w-3xl mx-auto">
      {p.map && <p className="text-xs uppercase tracking-wide text-text-muted mb-2">{p.map.name}</p>}
      <div className="bg-bg-surface border border-border rounded-lg p-4 sm:p-5 mb-4">
        <div className="flex items-center gap-3">
          <Avatar src={p.avatar} alt={p.username} size="lg" />
          <div className="min-w-0">
            <h1 className="text-2xl sm:text-3xl font-display text-secondary truncate">Where&apos;s {p.username}?</h1>
            {p.live ? (
              <p className="text-text-muted text-sm">
                Updated {timeAgo(p.updated_at) || 'recently'}
              </p>
            ) : (
              <p className="text-text-muted text-sm">{p.username} {closedMessage(p.reason, p.map)}</p>
            )}
          </div>
        </div>
        {p.live && (
          <div className="mt-4">
            <p className="text-xl sm:text-2xl text-text-primary font-semibold">
              {p.label || (hasPin ? 'See the pin on the map' : 'Somewhere at the event')}
            </p>
            {p.note && <p className="text-text-muted mt-1">{p.note}</p>}
          </div>
        )}
      </div>

      {p.live && p.map && (
        <HallMap
          map={p.map}
          spots={p.map.spots}
          pins={hasPin ? [{ x: p.x, y: p.y, avatar: p.avatar, name: p.username }] : []}
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 mt-3 text-sm">
        <button type="button" onClick={load} className="text-primary hover:underline">Refresh</button>
        <span className="text-text-muted">Refreshes every minute</span>
      </div>
      <p className="text-text-muted text-sm mt-6">
        <Link to="/find" className="text-primary hover:underline">Share your own spot</Link>
        {' '}so friends can find you too.
      </p>
    </div>
  )
}
