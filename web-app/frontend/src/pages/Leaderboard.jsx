import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import LeaderboardTable from '@/components/leaderboard/LeaderboardTable'
import { StatBox, TrophyRuns, LimitedLeaderboardTable } from '@/components/leaderboard/LimitedLeaderboardContent'
import Spinner from '@/components/ui/Spinner'
import {
  getCombinedLeaderboard,
  getLimitedLeaderboard,
  getEvents,
  getArchivedLeaderboard,
  browseSeasons,
} from '@/api/leaderboard'
import usePageTitle from '@/hooks/usePageTitle'

// The page shows one board at a time, picked from the sidebar (a select on
// phones). The pick lives in the URL (?board=...) so a board can be linked.
const CURRENT = 'current'
const LIFETIME = 'lifetime'
const LIMITED = 'limited'
const SEASONS = 'seasons'
const eventKey = (eventId) => `event:${eventId}`

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString() : 'N/A'
}

function formatDateRange(start, end) {
  return `${formatDate(start)} - ${formatDate(end)}`
}

function plural(count, word, words = `${word}s`) {
  return `${count} ${count === 1 ? word : words}`
}

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
    <section className="mt-8">
      <h3 className="text-lg font-display text-secondary mb-2">ELO Distribution</h3>
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

// ── Board navigation ──────────────────────────────────────────

function BoardNav({ groups, selected, onSelect }) {
  return (
    <>
      {/* Phones: one picker */}
      <div className="lg:hidden mb-6">
        <label htmlFor="board-select" className="sr-only">Leaderboard</label>
        <select
          id="board-select"
          value={selected}
          onChange={(e) => onSelect(e.target.value)}
          className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm"
        >
          {groups.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.items.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.title}{item.meta ? ` · ${item.meta}` : ''}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {/* Desktop: sidebar */}
      <nav aria-label="Leaderboards" className="hidden lg:flex flex-col gap-6 w-72 shrink-0">
        {groups.map((group) => (
          <div key={group.label}>
            <div className="text-[10px] uppercase tracking-wider text-text-muted mb-2 px-1">{group.label}</div>
            <div className="flex flex-col gap-2">
              {group.items.map((item) => {
                const active = item.key === selected
                return (
                  <button
                    type="button"
                    key={item.key}
                    aria-current={active ? 'true' : undefined}
                    onClick={() => onSelect(item.key)}
                    className={`text-left rounded-soft border px-4 py-3 transition-colors ${
                      active ? 'bg-bg-elevated border-primary' : 'bg-bg-surface border-border hover:border-primary/50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">{item.title}</span>
                      {item.badge && (
                        <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-green-900/30 text-green-400">{item.badge}</span>
                      )}
                    </div>
                    {item.meta && <div className="text-xs text-text-muted mt-0.5">{item.meta}</div>}
                    {item.detail && <div className="text-xs text-text-muted">{item.detail}</div>}
                    {item.champion && (
                      <div className="text-xs text-yellow-300 mt-1 inline-flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-yellow-300" aria-hidden="true" />
                        {item.champion}
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>
    </>
  )
}

function BoardHeader({ title, meta, badge, children }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-4">
      <h2 className="text-xl font-display text-secondary">{title}</h2>
      {badge && (
        <span className="self-center text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-green-900/30 text-green-400">{badge}</span>
      )}
      {meta && <span className="text-sm text-text-muted">{meta}</span>}
      {children}
    </div>
  )
}

// ── Boards ────────────────────────────────────────────────────

function CurrentEventBoard({ eventData }) {
  const info = eventData?.info
  const rows = eventData?.leaderboard || []
  if (!info) {
    return (
      <section>
        <BoardHeader title="No Active Event" meta="ELO tracking is paused between events" />
        <p className="text-text-muted text-center py-8">The next event's standings will appear here once it starts.</p>
      </section>
    )
  }
  const players = new Set(rows.map((p) => p.id || p.user_id)).size
  const matches = rows.reduce((n, p) => n + (p.wins || 0), 0)
  return (
    <section>
      <BoardHeader
        title={info.event_name}
        badge="Live"
        meta={`Started ${formatDate(info.start_date)} · ${plural(players, 'player')} · ${plural(matches, 'match', 'matches')}`}
      />
      {rows.length > 0 ? (
        <LeaderboardTable data={rows} columns="event" voiceRequirement={eventData?.voice_requirement} />
      ) : (
        <p className="text-text-muted text-center py-8">No matches played yet</p>
      )}
    </section>
  )
}

function LifetimeBoard({ lifetimeData, elos }) {
  return (
    <section>
      <BoardHeader title="Lifetime ELO Leaderboard" meta="Cumulative rankings across all events" />
      <LeaderboardTable data={lifetimeData} columns="lifetime" />
      <EloDistribution elos={elos} />
    </section>
  )
}

function LimitedBoard({ limitedData }) {
  const leaderboard = limitedData.leaderboard || limitedData
  const trophyRuns = limitedData.trophy_runs || []
  const stats = limitedData.stats || {}
  return (
    <section>
      <BoardHeader title="Limited Format Leaderboard" meta="Arena draft rankings - lifetime ELO">
        <Link to="/elo/limited" className="text-sm text-primary hover:text-primary-light transition-colors">Full limited page</Link>
      </BoardHeader>
      {stats.unique_players > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatBox label="Players" value={stats.unique_players} />
          <StatBox label="Runs Completed" value={stats.total_runs} />
          <StatBox label="Matches Played" value={stats.total_matches} />
          <StatBox label="Trophy Runs (4-0)" value={stats.trophy_runs} />
        </div>
      )}
      <LimitedLeaderboardTable data={Array.isArray(leaderboard) ? leaderboard : []} />
      <TrophyRuns runs={trophyRuns} />
    </section>
  )
}

function ArchivedEventBoard({ event }) {
  const [archivedData, setArchivedData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const eventId = event.event_id

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(false)
    setArchivedData(null)
    getArchivedLeaderboard(eventId)
      .then((data) => { if (active) setArchivedData(data) })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [eventId])

  const info = archivedData?.event_info || event
  const rows = archivedData?.leaderboard || []
  const totalMatches = archivedData?.total_matches || 0
  const meta = [formatDateRange(info.start_date, info.end_date)]
  if (archivedData) {
    meta.push(plural(rows.length, 'player'))
    if (totalMatches > 0) meta.push(plural(totalMatches, 'match', 'matches'))
  }

  return (
    <section>
      <BoardHeader title={info.event_name} meta={meta.join(' · ')} />
      {loading && <Spinner className="py-8" />}
      {error && !loading && (
        <p className="text-text-muted text-center py-8">Couldn't load standings for this event.</p>
      )}
      {archivedData && !loading && (
        rows.length > 0 ? (
          <LeaderboardTable data={rows} columns="event" eloLabel={info.value_label || 'Event ELO'} />
        ) : (
          <p className="text-text-muted text-center py-8">No standings were archived for this event.</p>
        )
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
    <section>
      <BoardHeader title="Season Leaderboards" meta="Search for user-created seasons" />
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
                  {s.start_date} &mdash; {s.end_date} &middot; {memberText}{s.region ? ` · ${s.region}` : ''} &middot; by {s.creator_name}
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

function pastEventSummary(ev) {
  const parts = []
  if (ev.players != null) parts.push(plural(ev.players, 'player'))
  if (ev.matches != null) parts.push(plural(ev.matches, 'match', 'matches'))
  if (ev.value_label === 'Wins' || String(ev.event_id).startsWith('season_')) parts.push('ranked by wins')
  return parts.join(' · ')
}

export default function Leaderboard() {
  usePageTitle('ELO Leaderboards')
  const [searchParams, setSearchParams] = useSearchParams()
  const [lifetimeData, setLifetimeData] = useState([])
  const [eloValues, setEloValues] = useState([])
  const [eventData, setEventData] = useState(null)
  const [limitedData, setLimitedData] = useState(null)
  const [pastEvents, setPastEvents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAll = async () => {
      const [combined, limited, events] = await Promise.allSettled([
        getCombinedLeaderboard(),
        getLimitedLeaderboard(),
        getEvents(),
      ])
      if (combined.status === 'fulfilled') {
        const data = combined.value
        setLifetimeData(data.lifetime || [])
        setEloValues(data.elos || (data.lifetime || []).map((p) => p.elo))
        setEventData(data.event || null)
      }
      if (limited.status === 'fulfilled') setLimitedData(limited.value)
      else setLimitedData(null)
      if (events.status === 'fulfilled') {
        setPastEvents((events.value.events || []).filter((e) => !e.is_active))
      }
    }
    fetchAll().finally(() => setLoading(false))
  }, [])

  const elos = eloValues.length > 0 ? eloValues : lifetimeData.map((p) => p.elo)
  const eventInfo = eventData?.info
  const eventLeaderboard = eventData?.leaderboard || []

  const groups = useMemo(() => {
    const result = []
    if (eventInfo) {
      const players = new Set(eventLeaderboard.map((p) => p.id || p.user_id)).size
      const matches = eventLeaderboard.reduce((n, p) => n + (p.wins || 0), 0)
      result.push({
        label: 'Now',
        items: [{
          key: CURRENT,
          title: eventInfo.event_name,
          badge: 'Live',
          meta: `Started ${formatDate(eventInfo.start_date)}`,
          detail: `${plural(players, 'player')} · ${plural(matches, 'match', 'matches')}`,
        }],
      })
    } else {
      result.push({
        label: 'Now',
        items: [{ key: CURRENT, title: 'No active event', meta: 'ELO tracking is paused between events' }],
      })
    }
    const allTime = [{ key: LIFETIME, title: 'Lifetime ELO', meta: `${plural(lifetimeData.length, 'player')} · every event` }]
    if (limitedData) {
      const stats = limitedData.stats || {}
      allTime.push({
        key: LIMITED,
        title: 'Limited format',
        meta: stats.unique_players ? `Arena draft · ${plural(stats.unique_players, 'player')}` : 'Arena draft',
      })
    }
    result.push({ label: 'All time', items: allTime })
    if (pastEvents.length > 0) {
      result.push({
        label: 'Past events',
        items: pastEvents.map((ev) => ({
          key: eventKey(ev.event_id),
          title: ev.event_name,
          meta: formatDateRange(ev.start_date, ev.end_date),
          detail: pastEventSummary(ev),
          champion: ev.champion,
        })),
      })
    }
    result.push({ label: 'Community', items: [{ key: SEASONS, title: 'Season leaderboards', meta: 'User-created seasons' }] })
    return result
  }, [eventInfo, eventLeaderboard, lifetimeData, limitedData, pastEvents])

  const keys = useMemo(() => groups.flatMap((g) => g.items.map((i) => i.key)), [groups])
  const requested = searchParams.get('board') || CURRENT
  const selected = keys.includes(requested) ? requested : CURRENT

  const selectBoard = (key) => {
    const next = new URLSearchParams(searchParams)
    if (key === CURRENT) next.delete('board')
    else next.set('board', key)
    setSearchParams(next)
  }

  if (loading) return <Spinner className="py-20" />

  const selectedEvent = selected.startsWith('event:')
    ? pastEvents.find((ev) => eventKey(ev.event_id) === selected)
    : null

  return (
    <div>
      <section className="mb-6">
        <h1 className="text-2xl font-display text-secondary">ELO Leaderboards</h1>
        <p className="text-sm text-text-muted">Track player rankings across events</p>
      </section>

      <div className="lg:flex lg:gap-8 lg:items-start">
        <BoardNav groups={groups} selected={selected} onSelect={selectBoard} />
        <div className="flex-1 min-w-0">
          {selected === CURRENT && <CurrentEventBoard eventData={eventData} />}
          {selected === LIFETIME && <LifetimeBoard lifetimeData={lifetimeData} elos={elos} />}
          {selected === LIMITED && limitedData && <LimitedBoard limitedData={limitedData} />}
          {selectedEvent && <ArchivedEventBoard key={selectedEvent.event_id} event={selectedEvent} />}
          {selected === SEASONS && <SeasonSearch />}
        </div>
      </div>
    </div>
  )
}
