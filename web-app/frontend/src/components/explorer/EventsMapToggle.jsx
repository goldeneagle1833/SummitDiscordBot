import { useState, useEffect, useCallback } from 'react'
import {
  fetchExplorerSettings,
  updateExplorerSettings,
  fetchUnmappedEvents,
  geocodeEvent,
} from '@/api/explorer'

/**
 * Controls whether the Community Series page shows its events map, and lets
 * an admin place any events that failed to geocode on import.
 */
export default function EventsMapToggle() {
  const [enabled, setEnabled] = useState(false)
  const [unmapped, setUnmapped] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [settings, missing] = await Promise.all([
        fetchExplorerSettings(),
        fetchUnmappedEvents().catch(() => ({ events: [] })),
      ])
      setEnabled(Boolean(settings.events_map_enabled))
      setUnmapped(missing.events || [])
      setError(null)
    } catch (err) {
      setError(err.message || 'Could not load map settings')
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = async () => {
    const next = !enabled
    setSaving(true)
    setError(null)
    try {
      const data = await updateExplorerSettings(next)
      setEnabled(Boolean(data.events_map_enabled))
    } catch (err) {
      setError(err.message || 'Could not save that')
    }
    setSaving(false)
  }

  const place = async (event) => {
    setBusyId(event.id)
    setError(null)
    try {
      await geocodeEvent(event.id)
      setUnmapped((list) => list.filter((e) => e.id !== event.id))
    } catch (err) {
      setError(err.message || `Could not place ${event.event_name}`)
    }
    setBusyId(null)
  }

  return (
    <section className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Community Series events map</h2>
          <p className="text-xs text-text-muted">
            Shows a map of past events at the top of the public Community Series page.
          </p>
        </div>
        <button
          onClick={toggle}
          disabled={loading || saving}
          role="switch"
          aria-checked={enabled}
          aria-label="Show events map on the Community Series page"
          className={`px-3 py-1.5 text-sm rounded border transition-colors disabled:opacity-40 ${
            enabled
              ? 'border-emerald-400/40 bg-emerald-400/15 text-emerald-300'
              : 'border-border text-text-muted hover:border-secondary'
          }`}
        >
          {loading ? 'Loading…' : enabled ? 'Map is on' : 'Map is off'}
        </button>
      </div>

      {error && <p className="text-xs text-accent-red">{error}</p>}

      {unmapped.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-text-muted">
            {unmapped.length} event{unmapped.length === 1 ? '' : 's'} not on the map yet.
            Events are placed from their venue name when imported.
          </p>
          <ul className="space-y-1">
            {unmapped.map((event) => (
              <li
                key={event.id}
                className="flex flex-wrap items-center gap-2 text-sm border-b border-border/50 pb-1"
              >
                <span className="flex-1 text-text-primary">{event.event_name}</span>
                <span className="text-xs text-text-muted">
                  {event.venue_name || 'no venue recorded'}
                </span>
                <button
                  onClick={() => place(event)}
                  disabled={busyId === event.id || !event.venue_name}
                  className="text-xs text-primary hover:underline disabled:opacity-40 disabled:no-underline"
                >
                  {busyId === event.id ? 'Placing…' : 'Place on map'}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
