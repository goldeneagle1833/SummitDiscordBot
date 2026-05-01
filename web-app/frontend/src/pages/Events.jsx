import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { getEvents } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const YEARS = ['2026', '2025', '2024', '2023']
const FORMATS = ['cornerstone', 'crossroads']

export default function Events() {
  usePageTitle('Top 8 Decks by Event')
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [yearFilter, setYearFilter] = useState('')
  const [formatFilter, setFormatFilter] = useState('')

  useEffect(() => {
    getEvents()
      .then(setEvents)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    return events.filter((ev) => {
      const combined = ((ev.name || '') + ' ' + (ev.folder || '')).toLowerCase()
      if (yearFilter && !combined.includes(yearFilter)) return false
      if (formatFilter && !combined.includes(formatFilter)) return false
      return true
    })
  }, [events, yearFilter, formatFilter])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Hero */}
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary mb-2">Top 8 Decks by Event</h1>
        <p className="text-text-muted text-sm">Browse winning decks from competitive events</p>
        <p className="text-text-muted/50 text-xs mt-1">
          Want to see your event here? Send me a list of Curiosa deck URLs on the{' '}
          <a href="https://discord.gg/ZDqHSK9VGx" target="_blank" rel="noopener noreferrer" className="text-[#5865f2] hover:underline">
            Summit Discord
          </a>{' '}
          and I'll be happy to add them!
        </p>
      </section>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-4 mb-4 p-3 bg-bg-surface rounded-lg border border-border">
        <div>
          <label className="text-xs text-text-muted block mb-1">Year</label>
          <select
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
            value={yearFilter}
            onChange={(e) => setYearFilter(e.target.value)}
          >
            <option value="">All Years</option>
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">Format</label>
          <select
            className="bg-bg-raised border border-border rounded px-3 py-1.5 text-sm"
            value={formatFilter}
            onChange={(e) => setFormatFilter(e.target.value)}
          >
            <option value="">All Formats</option>
            {FORMATS.map((f) => <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>)}
          </select>
        </div>
        <span className="text-text-muted text-xs ml-auto self-end pb-1">
          {filtered.length} of {events.length} events
        </span>
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <p className="text-center text-text-muted py-8">No events match your filters.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((event) => {
            const stars = event.rating || 1
            return (
              <Link
                key={event.folder}
                to={`/top-8/${event.folder}`}
                className="bg-bg-surface border border-border rounded-lg p-4 hover:border-primary/50 hover:-translate-y-0.5 transition-all"
              >
                <h3 className="font-semibold truncate mb-1">{event.name || event.folder}</h3>
                <div className="flex gap-0.5 mb-1">
                  {[1, 2, 3].map((i) => (
                    <span key={i} className={i <= stars ? 'text-yellow-400' : 'text-white/20'}>★</span>
                  ))}
                </div>
                <div className="text-sm text-text-muted">
                  {event.player_count || 0} decks
                </div>
                {event.has_top8 && (
                  <span className="inline-block mt-1.5 text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">
                    Top 8 Available
                  </span>
                )}
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
