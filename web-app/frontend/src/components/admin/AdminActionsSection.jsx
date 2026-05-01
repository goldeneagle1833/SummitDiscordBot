import { useState, useEffect } from 'react'
import { get, post } from '@/api/client'

export default function AdminActionsSection({ onRefresh }) {
  const [activeEvent, setActiveEvent] = useState(undefined) // undefined = loading
  const [eventName, setEventName] = useState('')
  const [activityHours, setActivityHours] = useState(24)
  const [activityResult, setActivityResult] = useState(null)
  const [activityLoading, setActivityLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(null)

  useEffect(() => {
    get('/api/events')
      .then(d => setActiveEvent(d.active_event || null))
      .catch(() => setActiveEvent(null))
  }, [])

  const handleResetAll = async () => {
    if (!confirm(
      '⚠️ WARNING: This will DELETE ALL ELO ratings and match history!\n\nThis action CANNOT be undone!\n\nAre you absolutely sure?'
    )) return
    if (!confirm(
      'This is your FINAL warning. ALL data will be permanently deleted.\n\nClick OK to confirm.'
    )) return
    const input = prompt('Type YES to confirm database reset:')
    if (input !== 'YES') { alert('Reset cancelled.'); return }

    setActionLoading('reset')
    try {
      const d = await post('/api/admin/reset-all-elo', {})
      if (d.success) {
        alert('✅ ' + d.message)
        onRefresh?.()
      } else {
        alert('❌ Error: ' + d.error)
      }
    } catch {
      alert('❌ Request failed')
    }
    setActionLoading(null)
  }

  const handleActivity = async () => {
    setActivityLoading(true)
    setActivityResult(null)
    try {
      const d = await get(`/api/admin/game-activity?hours=${activityHours}`)
      setActivityResult(d)
    } catch {
      setActivityResult({ success: false, error: 'Request failed' })
    }
    setActivityLoading(false)
  }

  const handleStartEvent = async () => {
    if (!eventName.trim()) { alert('Please enter an event name.'); return }
    if (!confirm(
      `Start new event "${eventName}"?\n\nThis will archive the current event (if any) and reset event ELO for all players.`
    )) return

    setActionLoading('start')
    try {
      const d = await post('/api/admin/start-event', { event_name: eventName.trim() })
      if (d.success) {
        alert('✅ ' + d.message)
        setEventName('')
        setActiveEvent({ event_name: eventName.trim() })
        onRefresh?.()
      } else {
        alert('❌ Error: ' + d.error)
      }
    } catch {
      alert('❌ Request failed')
    }
    setActionLoading(null)
  }

  const handleEndEvent = async () => {
    if (!confirm(
      'End the current event?\n\nThis will archive the event and leave no active event until you start a new one.'
    )) return

    setActionLoading('end')
    try {
      const d = await post('/api/admin/end-event', {})
      if (d.success) {
        alert('✅ ' + d.message)
        setActiveEvent(null)
        onRefresh?.()
      } else {
        alert('❌ Error: ' + d.error)
      }
    } catch {
      alert('❌ Request failed')
    }
    setActionLoading(null)
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-text-primary">Admin Actions</h2>
        <p className="text-xs text-text-muted">Perform administrative operations</p>
      </div>

      {/* Active event status */}
      {activeEvent !== undefined && (
        <div className={`px-4 py-2 rounded text-sm border ${
          activeEvent
            ? 'bg-accent-green/10 border-accent-green/30 text-accent-green'
            : 'bg-bg-raised border-border text-text-muted'
        }`}>
          {activeEvent
            ? `📅 Current Event: ${activeEvent.event_name}${activeEvent.event_id ? ` (ID: ${activeEvent.event_id})` : ''}`
            : 'ℹ️ No active event'}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Full reset */}
        <div className="bg-bg-raised border border-accent-red/30 rounded-lg p-4 space-y-2">
          <h3 className="text-sm font-semibold text-accent-red">⚠️ Full Database Reset</h3>
          <p className="text-xs text-text-muted">
            DANGER: Completely reset ALL ELO ratings and match history. This cannot be undone!
          </p>
          <button
            onClick={handleResetAll}
            disabled={actionLoading === 'reset'}
            className="px-3 py-1.5 text-xs bg-accent-red text-white rounded hover:opacity-90 disabled:opacity-40"
          >
            {actionLoading === 'reset' ? 'Resetting...' : 'Reset All Data'}
          </button>
        </div>

        {/* Activity monitoring */}
        <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-2">
          <h3 className="text-sm font-semibold">📊 Activity Monitoring</h3>
          <p className="text-xs text-text-muted">View game statistics for the last X hours</p>
          <div className="flex gap-2 items-center">
            <input
              type="number"
              value={activityHours}
              onChange={e => setActivityHours(Math.max(1, Math.min(8760, Number(e.target.value))))}
              className="w-20 bg-bg-surface border border-border rounded px-2 py-1 text-sm"
              min={1}
              max={8760}
            />
            <span className="text-xs text-text-muted">hours</span>
            <button
              onClick={handleActivity}
              disabled={activityLoading}
              className="px-3 py-1.5 text-xs bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
            >
              {activityLoading ? 'Loading...' : 'View Activity'}
            </button>
          </div>
          {activityResult?.success && (
            <div className="text-xs space-y-0.5 bg-bg-surface rounded p-2">
              <div className="font-semibold">Last {activityResult.hours} hours</div>
              <div>
                Total: <strong>{activityResult.total_matches}</strong>
                {' · '}Online: {activityResult.bot_matches}
                {' · '}Paper: {activityResult.web_matches}
              </div>
              <div>Active Players: <strong>{activityResult.active_players}</strong></div>
              <div className="text-text-muted opacity-70">
                {activityResult.start_time} → {activityResult.end_time}
              </div>
            </div>
          )}
          {activityResult && !activityResult.success && (
            <p className="text-xs text-accent-red">{activityResult.error}</p>
          )}
        </div>

        {/* Start event */}
        <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-2">
          <h3 className="text-sm font-semibold">🎯 Start New Event</h3>
          <p className="text-xs text-text-muted">
            Archives current event (if any) and resets event ELO for all players.
          </p>
          <input
            value={eventName}
            onChange={e => setEventName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleStartEvent()}
            placeholder="e.g. Spring 2026 Championship"
            className="w-full bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
            maxLength={100}
          />
          <button
            onClick={handleStartEvent}
            disabled={actionLoading === 'start'}
            className="px-3 py-1.5 text-xs bg-accent-green text-white rounded hover:opacity-90 disabled:opacity-40"
          >
            {actionLoading === 'start' ? 'Starting...' : 'Start Event'}
          </button>
        </div>

        {/* End event */}
        <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-2">
          <h3 className="text-sm font-semibold">🏁 End Current Event</h3>
          <p className="text-xs text-text-muted">
            End the current event without starting a new one. For breaks between seasons.
          </p>
          <button
            onClick={handleEndEvent}
            disabled={actionLoading === 'end' || !activeEvent}
            className="px-3 py-1.5 text-xs bg-yellow-500 text-white rounded hover:opacity-90 disabled:opacity-40"
          >
            {actionLoading === 'end' ? 'Ending...' : 'End Event'}
          </button>
        </div>
      </div>
    </section>
  )
}
