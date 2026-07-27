import { useState, useEffect } from 'react'
import Spinner from '@/components/ui/Spinner'
import { getLimitedLeaderboard, getArchivedLimitedEvents, getArchivedLimitedLeaderboard } from '@/api/leaderboard'
import { StatBox, TrophyRuns, LimitedLeaderboardTable } from '@/components/leaderboard/LimitedLeaderboardContent'
import usePageTitle from '@/hooks/usePageTitle'

export default function LimitedLeaderboard() {
  usePageTitle('Limited Leaderboard')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('lifetime')
  const [switching, setSwitching] = useState(false)
  const [archivedEvents, setArchivedEvents] = useState([])
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [archivedData, setArchivedData] = useState(null)
  const [archivedLoading, setArchivedLoading] = useState(false)

  useEffect(() => {
    Promise.all([
      getLimitedLeaderboard(view).catch(() => null),
      getArchivedLimitedEvents().catch(() => ({ events: [] })),
    ]).then(([lb, events]) => {
      setData(lb)
      setArchivedEvents(events?.events || [])
      setLoading(false)
    })
  }, [])

  const switchView = (newView) => {
    if (newView === view) return
    setView(newView)
    setSwitching(true)
    getLimitedLeaderboard(newView)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setSwitching(false))
  }

  const loadArchivedEvent = (eventId) => {
    if (selectedEvent === eventId) {
      setSelectedEvent(null)
      setArchivedData(null)
      return
    }
    setSelectedEvent(eventId)
    setArchivedLoading(true)
    getArchivedLimitedLeaderboard(eventId)
      .then(setArchivedData)
      .catch(() => setArchivedData(null))
      .finally(() => setArchivedLoading(false))
  }

  if (loading) return <Spinner className="py-20" />

  if (!data) {
    return (
      <div className="text-center py-20">
        <h1 className="text-2xl font-display text-secondary mb-2">Limited Leaderboard</h1>
        <p className="text-text-muted">Limited leaderboard is not currently available.</p>
      </div>
    )
  }

  const leaderboard = data.leaderboard || data
  const trophyRuns = data.trophy_runs || []
  const stats = data.stats || {}

  return (
    <div>
      <section className="text-center mb-8">
        <h1 className="text-2xl font-display text-secondary">Limited Leaderboard</h1>
        <p className="text-sm text-text-muted">Arena draft rankings</p>
      </section>

      {/* View Toggle */}
      <div className="flex justify-center gap-2 mb-6">
        <button
          onClick={() => switchView('season')}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
            view === 'season'
              ? 'bg-secondary text-white'
              : 'bg-surface border border-border text-text-muted hover:border-secondary/50'
          }`}
        >
          Current Season
        </button>
        <button
          onClick={() => switchView('lifetime')}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
            view === 'lifetime'
              ? 'bg-secondary text-white'
              : 'bg-surface border border-border text-text-muted hover:border-secondary/50'
          }`}
        >
          Lifetime
        </button>
      </div>

      {/* Stats Overview */}
      {stats.unique_players > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          <StatBox label="Players" value={stats.unique_players} />
          <StatBox label="Runs Completed" value={stats.total_runs} />
          <StatBox label="Matches Played" value={stats.total_matches} />
          <StatBox label="Trophy Runs (4-0)" value={stats.trophy_runs} />
        </div>
      )}

      {/* Leaderboard */}
      <section className="mb-8">
        <h2 className="text-xl font-display text-secondary mb-1">
          {view === 'season' ? 'Current Season' : 'Lifetime'} Limited ELO
        </h2>
        <p className="text-sm text-text-muted mb-4">
          {view === 'season'
            ? 'Rankings for the current limited season'
            : 'Cumulative limited format rankings across all seasons'}
        </p>
        {switching ? (
          <Spinner className="py-8" />
        ) : (
          <LimitedLeaderboardTable data={Array.isArray(leaderboard) ? leaderboard : []} />
        )}
      </section>

      {/* Trophy Runs */}
      <TrophyRuns runs={trophyRuns} />

      {/* Past Limited Events */}
      {archivedEvents.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xl font-display text-secondary mb-4">Past Limited Events</h2>
          <div className="space-y-2">
            {archivedEvents.map((event) => (
              <div key={event.event_id}>
                <button
                  onClick={() => loadArchivedEvent(event.event_id)}
                  className={`w-full text-left px-4 py-3 rounded border transition-colors ${
                    selectedEvent === event.event_id
                      ? 'border-secondary bg-secondary/10'
                      : 'border-border hover:border-secondary/50'
                  }`}
                >
                  <span className="font-medium text-text">{event.event_name || `Event #${event.event_id}`}</span>
                  {event.archived_at && (
                    <span className="text-sm text-text-muted ml-2">
                      ({new Date(event.archived_at).toLocaleDateString()})
                    </span>
                  )}
                </button>
                {selectedEvent === event.event_id && (
                  <div className="mt-2 ml-2">
                    {archivedLoading ? (
                      <Spinner className="py-4" />
                    ) : archivedData?.leaderboard?.length > 0 ? (
                      <LimitedLeaderboardTable data={archivedData.leaderboard} />
                    ) : (
                      <p className="text-sm text-text-muted py-2">No standings data for this event.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
