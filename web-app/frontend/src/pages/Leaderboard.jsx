import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import LeaderboardTable from '@/components/leaderboard/LeaderboardTable'
import Spinner from '@/components/ui/Spinner'
import {
  getCombinedLeaderboard,
  getLeaderboard,
  getLimitedLeaderboard,
  getEvents,
  getArchivedLeaderboard,
  browseSeasons,
} from '@/api/leaderboard'
import usePageTitle from '@/hooks/usePageTitle'

// ── ELO Distribution helpers ──────────────────────────────────

function calculateDistribution(elos, startValue, bandSize) {
  if (!elos.length) return []
  const maxElo = Math.max(...elos)
  const bands = []
  for (let lower = startValue; lower <= maxElo + bandSize; lower += bandSize) {
    const upper = lower + bandSize - 1
    const count = elos.filter((e) => e >= lower && e <= upper).length
    bands.push({ range: `${lower}-${upper}`, count, percentage: ((count / elos.length) * 100).toFixed(2) })
  }
  return bands.filter((b) => b.count > 0 || parseInt(b.range) <= 1600).reverse()
}

const GROUPING_OPTIONS = [
  { value: '100-standard', label: '100pt (1100, 1200, ...)', start: 1100, size: 100 },
  { value: '100-offset', label: '100pt offset (1050, 1150, ...)', start: 1050, size: 100 },
  { value: '50-standard', label: '50pt (1100, 1150, ...)', start: 1100, size: 50 },
  { value: 'custom', label: 'Custom' },
]

function EloDistribution({ elos }) {
  const [grouping, setGrouping] = useState('100-standard')
  const [customStart, setCustomStart] = useState(1100)
  const [customSize, setCustomSize] = useState(100)

  const preset = GROUPING_OPTIONS.find((o) => o.value === grouping)
  const start = grouping === 'custom' ? customStart : preset.start
  const size = grouping === 'custom' ? customSize : preset.size
  const bands = calculateDistribution(elos, start, size)

  return (
    <section className="mb-8">
      <h2 className="text-xl font-display text-secondary mb-2">ELO Distribution</h2>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <label className="text-sm text-text-muted">Grouping:</label>
        <select
          value={grouping}
          onChange={(e) => setGrouping(e.target.value)}
          className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
        >
          {GROUPING_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {grouping === 'custom' && (
          <div className="flex items-center gap-2">
            <label className="text-sm text-text-muted">Start:</label>
            <input type="number" value={customStart} onChange={(e) => setCustomStart(Number(e.target.value))} step={50} min={1000} max={2000} className="bg-bg-surface border border-border rounded px-2 py-1 text-sm w-20" />
            <label className="text-sm text-text-muted">Size:</label>
            <input type="number" value={customSize} onChange={(e) => setCustomSize(Number(e.target.value))} step={25} min={25} max={500} className="bg-bg-surface border border-border rounded px-2 py-1 text-sm w-20" />
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-border">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">ELO Range</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Players (of {elos.length})</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">% of players</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {bands.map((b) => (
              <tr key={b.range} className="hover:bg-bg-elevated transition-colors">
                <td className="px-3 py-2 text-sm">{b.range}</td>
                <td className="px-3 py-2 text-sm">{b.count}</td>
                <td className="px-3 py-2 text-sm">{b.percentage}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Archived Events Section ───────────────────────────────────

function ArchivedEvents() {
  const [events, setEvents] = useState([])
  const [selectedEvent, setSelectedEvent] = useState('')
  const [archivedData, setArchivedData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getEvents()
      .then((data) => {
        const past = (data.events || []).filter((e) => !e.is_active)
        setEvents(past)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedEvent) { setArchivedData(null); return }
    setLoading(true)
    getArchivedLeaderboard(selectedEvent)
      .then(setArchivedData)
      .catch(() => setArchivedData(null))
      .finally(() => setLoading(false))
  }, [selectedEvent])

  return (
    <section className="mb-8">
      <h2 className="text-xl font-display text-secondary mb-1">Past Event Leaderboards</h2>
      <p className="text-sm text-text-muted mb-4">View final standings from completed events</p>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <label className="text-sm text-text-muted">Select Event:</label>
        <select
          value={selectedEvent}
          onChange={(e) => setSelectedEvent(e.target.value)}
          className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
        >
          <option value="">-- Select a Past Event --</option>
          {events.map((ev) => (
            <option key={ev.event_id} value={ev.event_id}>
              {ev.event_name} ({new Date(ev.start_date).toLocaleDateString()} - {ev.end_date ? new Date(ev.end_date).toLocaleDateString() : 'N/A'})
            </option>
          ))}
        </select>
      </div>
      {loading && <Spinner className="py-8" />}
      {archivedData && !loading && (
        <LeaderboardTable data={archivedData.leaderboard || []} columns="event" />
      )}
    </section>
  )
}

// ── Season Search Section ─────────────────────────────────────

function SeasonSearch() {
  const [query, setQuery] = useState('')
  const [seasons, setSeasons] = useState([])
  const [timer, setTimer] = useState(null)

  const fetchSeasons = useCallback((q) => {
    browseSeasons(q)
      .then((data) => setSeasons(data.seasons || []))
      .catch(() => setSeasons([]))
  }, [])

  useEffect(() => { fetchSeasons('') }, [fetchSeasons])

  const handleInput = (val) => {
    setQuery(val)
    if (timer) clearTimeout(timer)
    setTimer(setTimeout(() => fetchSeasons(val.trim()), 300))
  }

  return (
    <section className="mb-8">
      <h2 className="text-xl font-display text-secondary mb-1">Season Leaderboards</h2>
      <p className="text-sm text-text-muted mb-4">Search for user-created seasons</p>
      <input
        type="text"
        value={query}
        onChange={(e) => handleInput(e.target.value)}
        placeholder="Search seasons by name..."
        className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm mb-4"
      />
      {seasons.length === 0 ? (
        <p className="text-text-muted text-center py-4">No seasons found</p>
      ) : (
        <div className="space-y-2">
          {seasons.slice(-3).map((s) => {
            const memberText = s.max_members ? `${s.member_count}/${s.max_members} members` : `${s.member_count} members`
            let statusLabel = 'Active'
            if (s.status === 'ended') statusLabel = 'Ended'
            else if (s.start_date > new Date().toISOString().slice(0, 10)) statusLabel = 'Upcoming'

            return (
              <Link
                key={s.season_id}
                to={`/season/${s.season_id}`}
                className="block bg-bg-surface border border-border rounded-soft p-3 hover:border-primary/50 transition-colors"
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="font-medium text-sm">{s.title}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${s.status === 'ended' ? 'bg-red-900/30 text-red-400' : 'bg-green-900/30 text-green-400'}`}>
                    {statusLabel}
                  </span>
                </div>
                <div className="text-xs text-text-muted">
                  {s.start_date} &mdash; {s.end_date} &middot; {memberText}{s.region ? ` \u00b7 ${s.region}` : ''} &middot; by {s.creator_name}
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </section>
  )
}

// ── Main Leaderboard Page ─────────────────────────────────────

export default function Leaderboard() {
  usePageTitle('ELO Leaderboards')
  const [lifetimeData, setLifetimeData] = useState([])
  const [eloValues, setEloValues] = useState([])
  const [eventData, setEventData] = useState(null)
  const [limitedData, setLimitedData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAll = async () => {
      const [combined, limited] = await Promise.allSettled([
        getCombinedLeaderboard(),
        getLimitedLeaderboard(),
      ])
      if (combined.status === 'fulfilled') {
        const data = combined.value
        setLifetimeData(data.lifetime || [])
        setEloValues(data.elos || (data.lifetime || []).map((p) => p.elo))
        setEventData(data.event || null)
      }
      if (limited.status === 'fulfilled') setLimitedData(limited.value)
      else setLimitedData(null)
    }
    fetchAll().finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />

  const elos = eloValues.length > 0 ? eloValues : lifetimeData.map((p) => p.elo)
  const eventInfo = eventData?.info
  const eventLeaderboard = eventData?.leaderboard || []

  return (
    <div>
      <section className="text-center mb-8">
        <h1 className="text-2xl font-display text-secondary">ELO Leaderboards</h1>
        <p className="text-sm text-text-muted">Track player rankings across events</p>
      </section>

      {/* ELO Distribution */}
      <EloDistribution elos={elos} />

      {/* Lifetime Leaderboard */}
      <section className="mb-8">
        <h2 className="text-xl font-display text-secondary mb-1">Lifetime ELO Leaderboard</h2>
        <p className="text-sm text-text-muted mb-4">Cumulative rankings across all events</p>
        <LeaderboardTable data={lifetimeData} columns="lifetime" />
      </section>

      {/* Event Leaderboard */}
      <section className="mb-8">
        <h2 className="text-xl font-display text-secondary mb-1">
          {eventInfo ? eventInfo.event_name : 'No Active Event'}
        </h2>
        <p className="text-sm text-text-muted mb-4">
          {eventInfo
            ? `Started: ${new Date(eventInfo.start_date).toLocaleDateString()}`
            : 'ELO tracking is paused between events'}
        </p>
        {eventLeaderboard.length > 0 ? (
          <LeaderboardTable data={eventLeaderboard} columns="event" />
        ) : (
          <p className="text-text-muted text-center py-8">No matches played yet</p>
        )}
      </section>

      {/* Limited Leaderboard */}
      {limitedData !== null && (
        <section className="mb-8">
          <h2 className="text-xl font-display text-secondary mb-1">Limited Format Leaderboard</h2>
          <p className="text-sm text-text-muted mb-4">Rankings for limited format matches</p>
          <LeaderboardTable data={limitedData} columns="lifetime" />
        </section>
      )}

      {/* Archived Events */}
      <ArchivedEvents />

      {/* Season Search */}
      <SeasonSearch />
    </div>
  )
}
