import { useState } from 'react'
import { fetchVenueAttendance } from '@/api/explorer'
import Spinner from '@/components/ui/Spinner'

function AttendanceBar({ event, maxPlayers }) {
  const pct = maxPlayers > 0 ? (event.player_count / maxPlayers) * 100 : 0
  const tierColors = {
    Social: 'bg-blue-500',
    Local: 'bg-green-500',
    Regional: 'bg-yellow-500',
    National: 'bg-red-500',
  }
  const barColor = tierColors[event.tier] || 'bg-secondary'

  return (
    <div className="flex items-center gap-2 group">
      <div className="w-20 text-xs text-text-muted flex-shrink-0 text-right">{event.date || '—'}</div>
      <div className="flex-1 flex items-center gap-2">
        <div className="flex-1 bg-bg-elevated rounded-sm h-5 relative overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-sm transition-all duration-300`}
            style={{ width: `${Math.max(pct, 2)}%` }}
          />
        </div>
        <span className="w-6 text-xs text-text-primary font-medium text-right">{event.player_count}</span>
      </div>
      <div
        className="hidden group-hover:block absolute z-10 bg-bg-surface border border-border rounded px-2 py-1 text-xs text-text-primary shadow-lg ml-24 -mt-8 max-w-xs whitespace-nowrap"
      >
        {event.title} ({event.tier})
      </div>
    </div>
  )
}

function TierLegend() {
  const tiers = [
    { name: 'Social', color: 'bg-blue-500' },
    { name: 'Local', color: 'bg-green-500' },
    { name: 'Regional', color: 'bg-yellow-500' },
    { name: 'National', color: 'bg-red-500' },
  ]
  return (
    <div className="flex gap-3 text-xs text-text-muted">
      {tiers.map(t => (
        <span key={t.name} className="flex items-center gap-1">
          <span className={`w-2.5 h-2.5 rounded-sm ${t.color}`} />
          {t.name}
        </span>
      ))}
    </div>
  )
}

export default function VenueAttendancePanel() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  const handleFetch = async (e) => {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const result = await fetchVenueAttendance(url.trim())
      setData(result)
    } catch (err) {
      setError(err.message || 'Failed to fetch venue attendance')
    } finally {
      setLoading(false)
    }
  }

  const maxPlayers = data ? Math.max(...data.events.map(e => e.player_count), 1) : 0
  const avgAttendance = data && data.events.length > 0
    ? (data.events.reduce((sum, e) => sum + e.player_count, 0) / data.events.length).toFixed(1)
    : 0
  const eventsWithPlayers = data ? data.events.filter(e => e.player_count > 0) : []
  const avgWithPlayers = eventsWithPlayers.length > 0
    ? (eventsWithPlayers.reduce((sum, e) => sum + e.player_count, 0) / eventsWithPlayers.length).toFixed(1)
    : 0

  return (
    <div>
      <form onSubmit={handleFetch} className="flex gap-2 mb-3">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://sorcerytcg.com/stores/..."
          className="flex-1 bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm text-text-primary placeholder-text-muted/50 focus:border-secondary focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !url.trim()}
          className="px-4 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-50"
        >
          {loading ? 'Fetching...' : 'Lookup'}
        </button>
      </form>

      {error && <p className="text-sm text-red-400 mb-3">{error}</p>}

      {loading && (
        <div className="flex items-center gap-2 text-sm text-text-muted py-4">
          <Spinner />
          <span>Fetching venue events and player counts... This may take a moment.</span>
        </div>
      )}

      {data && (
        <div>
          {/* Store info */}
          <div className="flex items-center justify-between mb-3">
            <div>
              <h4 className="text-base font-semibold text-text-primary">{data.store_name}</h4>
              <p className="text-xs text-text-muted">{data.address}</p>
            </div>
            <span className={`text-xs px-2 py-0.5 rounded border ${
              data.status === 'Approved'
                ? 'bg-green-500/10 text-green-400 border-green-500/30'
                : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30'
            }`}>
              {data.status}
            </span>
          </div>

          {/* Stats summary */}
          <div className="flex flex-wrap gap-4 text-xs text-text-muted mb-3">
            <span><span className="text-text-primary font-medium">{data.events.length}</span> total events</span>
            <span>Avg attendance: <span className="text-text-primary font-medium">{avgAttendance}</span></span>
            {eventsWithPlayers.length !== data.events.length && (
              <span>Avg (excl. zero): <span className="text-text-primary font-medium">{avgWithPlayers}</span></span>
            )}
            <span>Peak: <span className="text-text-primary font-medium">{maxPlayers}</span></span>
          </div>

          <TierLegend />

          {/* Attendance graph */}
          {data.events.length === 0 ? (
            <p className="text-sm text-text-muted py-4">No past events found for this venue.</p>
          ) : (
            <div className="mt-3 space-y-0.5 max-h-96 overflow-y-auto pr-1">
              {data.events.map((event, i) => (
                <AttendanceBar key={`${event.date}-${i}`} event={event} maxPlayers={maxPlayers} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
