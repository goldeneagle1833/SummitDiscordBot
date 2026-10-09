import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { DailyActiveUsersChart, ActiveUsersTiles, PageViewsPanel } from './AnalyticsSection'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'

/** Monday that starts a SQLite strftime('%Y-%W') week. */
function weekStart(yw) {
  const [year, week] = yw.split('-').map(Number)
  const jan1 = new Date(year, 0, 1)
  const firstMonday = new Date(jan1)
  firstMonday.setDate(jan1.getDate() + ((8 - jan1.getDay()) % 7))
  const target = new Date(firstMonday)
  target.setDate(firstMonday.getDate() + (week - 1) * 7)
  return target
}

function weekLabel(yw) {
  if (!yw) return ''
  return weekStart(yw).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
}

const DAY_MS = 86400000

/** Start of the window for the last `days` days, or null for all time. */
function rangeCutoff(days, now = new Date()) {
  return days == null ? null : new Date(now.getTime() - days * DAY_MS)
}

/** Weekly rows (with a `week` key) that overlap the last `days` days, labelled for the axis. */
export function weeksInRange(rows, days, now = new Date()) {
  const cutoff = rangeCutoff(days, now)
  return (rows || [])
    .filter(d => !cutoff || weekStart(d.week).getTime() + 7 * DAY_MS > cutoff.getTime())
    .map(d => ({ ...d, label: weekLabel(d.week) }))
}

export const RANGES = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 60 days', days: 60 },
  { label: 'Last 90 days', days: 90 },
  { label: 'All Time', days: null },
]

const TABS = [
  { key: 'site', label: 'Site Traffic' },
  { key: 'matches', label: 'Matches' },
  { key: 'players', label: 'Players' },
]

const STORAGE_KEY = 'admin-dashboard'

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}
  } catch {
    return {}
  }
}

function savePrefs(prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // storage blocked — preferences just won't stick
  }
}

function rangeLabel(days) {
  return days == null ? 'all time' : `last ${days} days`
}

const CHART_STYLE = {
  grid: { stroke: 'rgba(255,255,255,0.05)' },
  axis: { tick: { fill: 'rgba(255,255,255,0.4)', fontSize: 10 }, tickLine: false, axisLine: false },
  tooltip: { contentStyle: { background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, fontSize: 11 } },
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const HOURS = Array.from({ length: 24 }, (_, h) =>
  h === 0 ? '12a' : h < 12 ? `${h}a` : h === 12 ? '12p' : `${h - 12}p`
)

function heatColor(intensity) {
  if (intensity <= 0.5) {
    const t = intensity * 2
    return `rgb(220, ${Math.round(60 + t * 160)}, ${Math.round(50 + t * 10)})`
  }
  const t = (intensity - 0.5) * 2
  return `rgb(${Math.round(220 - t * 170)}, ${Math.round(220 - t * 30)}, ${Math.round(60 + t * 30)})`
}

function Heatmap({ data }) {
  if (!data?.length) return <p className="text-text-muted text-sm">No data.</p>
  const maxVal = Math.max(...data.flat(), 1)
  return (
    <div className="overflow-x-auto">
      <div
        className="inline-grid"
        style={{ gridTemplateColumns: '36px repeat(24, 1fr)', gap: 2, minWidth: 680 }}
      >
        <div />
        {HOURS.map(h => (
          <div key={h} className="text-center text-text-muted" style={{ fontSize: 8 }}>{h}</div>
        ))}
        {DAYS.map((day, d) => (
          <div key={day} className="contents">
            <div className="text-text-muted flex items-center" style={{ fontSize: 10 }}>{day}</div>
            {Array.from({ length: 24 }, (_, h) => {
              const val = data[d][h]
              const bg = val === 0 ? 'rgba(255,255,255,0.04)' : heatColor(val / maxVal)
              return (
                <div
                  key={h}
                  title={`${day} ${h}:00 — ${val} games`}
                  className="rounded flex items-center justify-center"
                  style={{ height: 22, background: bg, fontSize: 8, color: val > 0 ? 'rgba(0,0,0,0.65)' : 'transparent' }}
                >
                  {val || ''}
                </div>
              )
            })}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-1 mt-2 text-xs text-text-muted">
        <span>Less</span>
        {[0, 0.25, 0.5, 0.75, 1].map(v => (
          <div
            key={v}
            className="w-4 h-3 rounded-sm"
            style={{ background: v === 0 ? 'rgba(255,255,255,0.04)' : heatColor(v) }}
          />
        ))}
        <span>More</span>
      </div>
    </div>
  )
}

function DominancePanel({ dom }) {
  if (!dom?.total_players_with_wins) {
    return <p className="text-text-muted text-sm">Not enough data yet.</p>
  }

  const PlayerTable = ({ players }) => (
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-border text-text-muted">
          <th className="py-1 px-1 text-left">#</th>
          <th className="py-1 px-1 text-left">Player</th>
          <th className="py-1 px-1 text-center">W</th>
          <th className="py-1 px-1 text-center">L</th>
          <th className="py-1 px-1 text-center">G</th>
          <th className="py-1 px-1 text-center">Win%</th>
        </tr>
      </thead>
      <tbody>
        {(players || []).map((p, i) => (
          <tr key={i} className="border-b border-border/30">
            <td className="py-1 px-1 text-text-muted">{i + 1}</td>
            <td className="py-1 px-1 whitespace-nowrap">{p.name}</td>
            <td className="py-1 px-1 text-center">{p.wins}</td>
            <td className="py-1 px-1 text-center">{p.losses}</td>
            <td className="py-1 px-1 text-center">{p.games}</td>
            <td className="py-1 px-1 text-center font-bold">{p.win_rate}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <div className="space-y-3">
      <div className="flex gap-6 text-sm flex-wrap">
        <span>Players with wins: <strong>{dom.total_players_with_wins}</strong></span>
        <span className="text-secondary">
          Top 10% ({dom.top_10_pct_count}p): <strong>{dom.top_10_pct_win_share}% of wins</strong>
        </span>
        <span>Top 25% ({dom.top_25_pct_count}p): <strong>{dom.top_25_pct_win_share}% of wins</strong></span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <h4 className="text-xs font-semibold text-text-muted mb-2">Top 10 by Wins</h4>
          <PlayerTable players={dom.top_10_players} />
        </div>
        <div>
          <h4 className="text-xs font-semibold text-text-muted mb-2">Most Active</h4>
          <PlayerTable players={dom.most_active} />
        </div>
        <div>
          <h4 className="text-xs font-semibold text-text-muted mb-2">Win Streaks</h4>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-text-muted">
                <th className="py-1 px-1 text-left">#</th>
                <th className="py-1 px-1 text-left">Player</th>
                <th className="py-1 px-1 text-center">Best</th>
                <th className="py-1 px-1 text-center">Now</th>
              </tr>
            </thead>
            <tbody>
              {(dom.streaks || []).length > 0
                ? dom.streaks.map((s, i) => (
                    <tr key={i} className="border-b border-border/30">
                      <td className="py-1 px-1 text-text-muted">{i + 1}</td>
                      <td className="py-1 px-1 whitespace-nowrap">{s.name}</td>
                      <td className="py-1 px-1 text-center font-bold">{s.best_streak}</td>
                      <td className="py-1 px-1 text-center">
                        {s.current_streak > 0 ? `${s.current_streak} 🔥` : '-'}
                      </td>
                    </tr>
                  ))
                : (
                  <tr>
                    <td colSpan={4} className="py-2 text-center text-text-muted">No streaks of 3+ yet</td>
                  </tr>
                )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ChartCard({ title, to, children }) {
  return (
    <Link to={to} className="bg-bg-raised border border-border rounded-lg p-4 hover:border-secondary/50 transition-colors cursor-pointer block">
      <h3 className="text-sm font-semibold mb-3">{title}</h3>
      {children}
    </Link>
  )
}

function ActiveUsersCard() {
  const [count, setCount] = useState(null)

  useEffect(() => {
    const load = () => get('/api/analytics/active-users')
      .then(d => { if (d.success) setCount(d.active_users) })
      .catch(() => {})
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [])

  return (
    <Link to="/admin/active-connections" className="bg-bg-raised border border-border rounded-lg p-4 text-center relative hover:border-green-400/50 transition-colors cursor-pointer block">
      <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-green-400 animate-pulse" />
      <div className="text-2xl font-bold text-green-400">{count ?? '--'}</div>
      <div className="text-xs text-text-muted mt-1 leading-tight">Active Now</div>
    </Link>
  )
}

function SessionAnalyticsCard({ days }) {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    setStats(null)
    get(days != null ? `/api/analytics/session-analytics?hours=${days * 24}` : '/api/analytics/session-analytics')
      .then(d => { if (d.success) setStats(d) })
      .catch(() => {})
  }, [days])

  return (
    <Link to="/admin/session-analytics" className="bg-bg-raised border border-border rounded-lg p-4 text-center hover:border-blue-400/50 transition-colors cursor-pointer block">
      <div className="text-2xl font-bold text-blue-400">{stats?.bounce_rate != null ? `${stats.bounce_rate}%` : '--'}</div>
      <div className="text-xs text-text-muted mt-1 leading-tight">Bounce Rate</div>
    </Link>
  )
}

function UniqueUsersCard() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    get('/api/analytics/unique-visitors')
      .then(d => { if (d.success) setStats(d) })
      .catch(() => {})
  }, [])

  return (
    <Link to="/admin/unique-users" className="bg-bg-raised border border-border rounded-lg p-4 text-center hover:border-purple-400/50 transition-colors cursor-pointer block">
      <div className="text-2xl font-bold text-purple-400">{stats?.total?.toLocaleString() ?? '--'}</div>
      <div className="text-xs text-text-muted mt-1 leading-tight">Unique Users</div>
    </Link>
  )
}

const VOICE_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'ranked', label: 'Ranked' },
  { key: 'testing', label: 'Casual' },
  { key: 'points', label: 'Rumble (Omens)' },
  { key: 'rumble', label: 'Rumble' },
  { key: 'limited', label: 'Limited' },
]
const VOICE_QUEUES = VOICE_FILTERS.filter(f => f.key !== 'all')

function voiceSplit(counts, filter, acrossDays = false) {
  if (acrossDays) {
    return counts.reduce((acc, day) => {
      const c = voiceSplit(day, filter)
      return { voice: acc.voice + c.voice, no_voice: acc.no_voice + c.no_voice }
    }, { voice: 0, no_voice: 0 })
  }
  const queues = filter === 'all' ? VOICE_QUEUES.map(f => f.key) : [filter]
  return queues.reduce(
    (acc, q) => ({
      voice: acc.voice + (counts?.[q]?.voice || 0),
      no_voice: acc.no_voice + (counts?.[q]?.no_voice || 0),
    }),
    { voice: 0, no_voice: 0 },
  )
}

function voicePct({ voice, no_voice }) {
  const total = voice + no_voice
  return total ? `${Math.round((voice / total) * 100)}%` : '--'
}

function dayLabel(date) {
  const [y, m, d] = date.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function VoiceDayTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const { voice, no_voice } = payload[0].payload
  return (
    <div style={CHART_STYLE.tooltip.contentStyle} className="px-2 py-1">
      <div className="font-semibold mb-0.5">{label}</div>
      <div>Total: {voice + no_voice}</div>
      <div style={{ color: 'rgba(63,185,80,1)' }}>Voice: {voice} ({voicePct({ voice, no_voice })})</div>
      <div style={{ color: 'rgba(255,255,255,0.6)' }}>No voice: {no_voice}</div>
    </div>
  )
}

export function VoiceStatsCard({ days = null }) {
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    get('/api/admin/voice-stats')
      .then(d => { if (d.success) setStats(d) })
      .catch(() => {})
  }, [])

  const cutoff = days != null ? rangeCutoff(days).toISOString().slice(0, 10) : null
  const inRange = (stats?.days || []).filter(day => !cutoff || day.date > cutoff)
  // Season totals come from the server; a narrower range re-totals the visible days.
  const totals = cutoff
    ? Object.fromEntries(VOICE_QUEUES.map(f => [f.key, voiceSplit(inRange, f.key, true)]))
    : stats?.queues
  const rows = [
    ...VOICE_QUEUES.map(f => [f.label, voiceSplit(totals, f.key)]),
    ['Total', voiceSplit(totals, 'all')],
  ]
  const chartDays = inRange.map(day => ({
    label: dayLabel(day.date),
    ...voiceSplit(day, filter),
  }))

  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <h3 className="text-sm font-semibold mb-1">Voice vs No-Voice Games</h3>
          <p className="text-xs text-text-muted">
            Queue games this season, by day{days != null ? ` (${rangeLabel(days)})` : ''}
          </p>
        </div>
        <div className="flex gap-1" role="group" aria-label="Queue">
          {VOICE_FILTERS.map(f => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
              className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                filter === f.key
                  ? 'border-secondary text-secondary'
                  : 'border-border text-text-muted hover:text-text'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {!stats ? (
        <p className="text-text-muted text-sm">No data.</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
          <div className="lg:col-span-2">
            {chartDays.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartDays}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
                  <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
                  <YAxis {...CHART_STYLE.axis} allowDecimals={false} />
                  <Tooltip content={<VoiceDayTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="voice" name="Voice" stackId="v" fill="rgba(63,185,80,0.8)" />
                  <Bar dataKey="no_voice" name="No voice" stackId="v" fill="rgba(255,255,255,0.25)" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-text-muted text-sm">No queue games recorded yet.</p>
            )}
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-muted text-xs text-left border-b border-border">
                <th className="py-1 pr-3 font-semibold">Queue</th>
                <th className="py-1 px-3 text-right font-semibold">Voice</th>
                <th className="py-1 px-3 text-right font-semibold">No voice</th>
                <th className="py-1 pl-3 text-right font-semibold">% Voice</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, c]) => (
                <tr key={label} className={`border-b border-border/50 ${label === 'Total' ? 'font-semibold' : ''}`}>
                  <td className="py-1 pr-3">{label}</td>
                  <td className="py-1 px-3 text-right">{c.voice.toLocaleString()}</td>
                  <td className="py-1 px-3 text-right">{c.no_voice.toLocaleString()}</td>
                  <td className="py-1 pl-3 text-right">{voicePct(c)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatTile({ label, value, link, color = 'text-secondary' }) {
  const inner = (
    <>
      <div className={`text-2xl font-bold ${color}`}>{value ?? '--'}</div>
      <div className="text-xs text-text-muted mt-1 leading-tight">{label}</div>
    </>
  )
  return link ? (
    <Link to={link} className="bg-bg-raised border border-border rounded-lg p-4 text-center hover:border-secondary transition-colors cursor-pointer block">
      {inner}
    </Link>
  ) : (
    <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">{inner}</div>
  )
}

function TileGroup({ title, children }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">{children}</div>
    </div>
  )
}

function SiteTab({ days, activeUsers }) {
  return (
    <div className="space-y-6">
      <TileGroup title="Visitors">
        <ActiveUsersCard />
        <UniqueUsersCard />
        <SessionAnalyticsCard days={days} />
        <ActiveUsersTiles activeUsers={activeUsers} />
      </TileGroup>
      <PageViewsPanel days={days} />
    </div>
  )
}

function MatchesTab({ days, stats }) {
  const { summary, games_over_time, heatmap } = stats
  const gamesData = useMemo(() => weeksInRange(games_over_time, days), [games_over_time, days])
  const gamesInRange = gamesData.reduce((n, w) => n + (w.bot || 0) + (w.web || 0), 0)

  return (
    <div className="space-y-6">
      <TileGroup title="Match totals (all time)">
        <StatTile label="Total Matches" value={summary.total_matches?.toLocaleString()} />
        <StatTile label="Online Matches" value={summary.total_bot_matches?.toLocaleString()} />
        <StatTile label="Paper Matches" value={summary.total_web_matches?.toLocaleString()} />
        <StatTile label="Omens Matches" value={(summary.total_points_matches || 0).toLocaleString()} link="/admin/omens-matches" />
        <StatTile label="External Matches" value={(summary.total_external_matches || 0).toLocaleString()} link="/admin/external-matches" />
        <StatTile label="Avg Games/Week (12wk)" value={summary.avg_weekly_games} />
      </TileGroup>

      <ChartCard title={`Games Over Time — ${gamesInRange.toLocaleString()} in ${rangeLabel(days)}`} to="/admin/chart/games-over-time">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={gamesData}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
            <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
            <YAxis {...CHART_STYLE.axis} />
            <Tooltip {...CHART_STYLE.tooltip} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="bot" name="Online" stackId="a" fill="rgba(77,184,255,0.8)" radius={[0, 0, 2, 2]} />
            <Bar dataKey="web" name="Paper" stackId="a" fill="rgba(63,185,80,0.8)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <VoiceStatsCard days={days} />

      <div className="bg-bg-raised border border-border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-1">Peak Activity Hours</h3>
        <p className="text-xs text-text-muted mb-3">Matches by day of week and hour (all time, EST)</p>
        <Heatmap data={heatmap} />
      </div>
    </div>
  )
}

function PlayersTab({ days, stats }) {
  const { summary, players_over_time, new_players_per_week, avg_games_per_player, dominance } = stats
  const playersData = useMemo(() => weeksInRange(players_over_time, days), [players_over_time, days])
  const newPlayersData = useMemo(() => weeksInRange(new_players_per_week, days), [new_players_per_week, days])
  const avgGppData = useMemo(() => weeksInRange(avg_games_per_player, days), [avg_games_per_player, days])
  const newInRange = newPlayersData.reduce((n, w) => n + (w.count || 0), 0)

  return (
    <div className="space-y-6">
      <TileGroup title="Players">
        <StatTile label="Total Players (all time)" value={summary.total_players?.toLocaleString()} />
        <StatTile label={`New Players (${rangeLabel(days)})`} value={newInRange.toLocaleString()} color="text-orange-400" />
        <StatTile label="Users Logged In (all time)" value={(summary.total_logins || 0).toLocaleString()} />
      </TileGroup>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="Unique Players per Week" to="/admin/chart/unique-players">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={playersData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
              <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
              <YAxis {...CHART_STYLE.axis} />
              <Tooltip {...CHART_STYLE.tooltip} />
              <Line dataKey="combined" name="Unique Players" stroke="rgba(168,130,255,0.8)" dot={playersData.length < 15} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="New Player Acquisition" to="/admin/chart/new-players">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={newPlayersData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
              <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
              <YAxis {...CHART_STYLE.axis} />
              <Tooltip {...CHART_STYLE.tooltip} />
              <Bar dataKey="count" name="New Players" fill="rgba(255,136,68,0.8)" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard title="Avg Games per Player per Week" to="/admin/chart/avg-games-per-player">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={avgGppData}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
            <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
            <YAxis {...CHART_STYLE.axis} />
            <Tooltip {...CHART_STYLE.tooltip} />
            <Line dataKey="avg" name="Avg Games/Player" stroke="rgba(219,154,4,0.8)" dot={avgGppData.length < 15} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="bg-bg-raised border border-border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3">Top Player Dominance (all time)</h3>
        <DominancePanel dom={dominance} />
      </div>
    </div>
  )
}

function SegmentedButtons({ options, value, onChange, label }) {
  return (
    <div className="flex gap-1 flex-wrap" role="group" aria-label={label}>
      {options.map(o => (
        <button
          key={o.label}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={`px-3 py-1 text-xs rounded border transition-colors ${
            value === o.value
              ? 'bg-secondary text-black border-secondary'
              : 'bg-bg-raised border-border text-text-muted hover:border-secondary'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/**
 * Admin dashboard: one date range drives everything, the daily active users
 * chart sits on top, and the rest is split into Site Traffic / Matches / Players tabs.
 */
export default function DashboardSection() {
  const prefs = useMemo(loadPrefs, [])
  const [days, setDays] = useState(RANGES.some(r => r.days === prefs.days) ? prefs.days : 30)
  const [tab, setTab] = useState(TABS.some(t => t.key === prefs.tab) ? prefs.tab : 'site')
  const [activeUsers, setActiveUsers] = useState(null)
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState(null)

  useEffect(() => { savePrefs({ days, tab }) }, [days, tab])

  useEffect(() => {
    // All-time payload; the chart applies the range client-side.
    get('/api/analytics/stats')
      .then(d => { if (d?.success) setActiveUsers(d.active_users ?? null) })
      .catch(console.error)
    get('/api/admin/dashboard-stats')
      .then(d => (d?.success ? setStats(d) : setStatsError('')))
      .catch(e => setStatsError(e.message))
  }, [])

  const matchTab = (Body) => {
    if (statsError != null) {
      return <p className="text-text-muted text-sm">Dashboard unavailable{statsError ? `: ${statsError}` : '.'}</p>
    }
    if (!stats) return <Spinner className="py-12" />
    return <Body days={days} stats={stats} />
  }

  return (
    <section className="space-y-6">
      <div className="sticky top-0 z-10 bg-bg-base/95 backdrop-blur py-2 -my-2">
        <SegmentedButtons
          label="Date range"
          options={RANGES.map(r => ({ label: r.label, value: r.days }))}
          value={days}
          onChange={setDays}
        />
      </div>

      {activeUsers ? (
        <DailyActiveUsersChart daily={activeUsers.daily} days={days} />
      ) : null}

      <div>
        <div className="flex gap-1 border-b border-border mb-4" role="tablist">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm -mb-px border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-secondary text-secondary'
                  : 'border-transparent text-text-muted hover:text-text'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div role="tabpanel">
          {tab === 'site' && <SiteTab days={days} activeUsers={activeUsers} />}
          {tab === 'matches' && matchTab(MatchesTab)}
          {tab === 'players' && matchTab(PlayersTab)}
        </div>
      </div>
    </section>
  )
}
