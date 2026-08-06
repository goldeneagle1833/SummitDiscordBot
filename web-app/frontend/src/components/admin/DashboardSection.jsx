import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'

function weekLabel(yw) {
  if (!yw) return ''
  const [year, week] = yw.split('-').map(Number)
  const jan1 = new Date(year, 0, 1)
  const firstMonday = new Date(jan1)
  firstMonday.setDate(jan1.getDate() + ((8 - jan1.getDay()) % 7))
  const target = new Date(firstMonday)
  target.setDate(firstMonday.getDate() + (week - 1) * 7)
  return target.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
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

function ChartCard({ title, children }) {
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3">{title}</h3>
      {children}
    </div>
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

export default function DashboardSection() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/api/admin/dashboard-stats')
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-12" />
  if (error || !data?.success) return (
    <p className="text-text-muted text-sm">Dashboard unavailable{error ? `: ${error}` : '.'}</p>
  )

  const { summary, games_over_time, players_over_time, new_players_per_week, avg_games_per_player, dominance, heatmap } = data

  const gamesData = games_over_time.map(d => ({ ...d, label: weekLabel(d.week) }))
  const playersData = players_over_time.map(d => ({ ...d, label: weekLabel(d.week) }))
  const newPlayersData = new_players_per_week.map(d => ({ ...d, label: weekLabel(d.week) }))
  const avgGppData = avg_games_per_player.map(d => ({ ...d, label: weekLabel(d.week) }))

  const summaryCards = [
    { label: 'Total Players', value: summary.total_players?.toLocaleString() },
    { label: 'Total Matches', value: summary.total_matches?.toLocaleString() },
    { label: 'Avg Games/Week (12wk)', value: summary.avg_weekly_games },
    { label: 'Online Matches', value: summary.total_bot_matches?.toLocaleString() },
    { label: 'Paper Matches', value: summary.total_web_matches?.toLocaleString() },
    { label: 'Omens Matches', value: (summary.total_points_matches || 0).toLocaleString() },
    { label: 'External Matches', value: (summary.total_external_matches || 0).toLocaleString(), link: '/admin/external-matches' },
    { label: 'Users Logged In', value: (summary.total_logins || 0).toLocaleString() },
  ]

  return (
    <section className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-10 gap-3">
        <ActiveUsersCard />
        <UniqueUsersCard />
        {summaryCards.map(c => {
          const inner = (
            <>
              <div className="text-2xl font-bold text-secondary">{c.value ?? '--'}</div>
              <div className="text-xs text-text-muted mt-1 leading-tight">{c.label}</div>
            </>
          )
          return c.link ? (
            <Link key={c.label} to={c.link} className="bg-bg-raised border border-border rounded-lg p-4 text-center hover:border-secondary transition-colors cursor-pointer block">
              {inner}
            </Link>
          ) : (
            <div key={c.label} className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              {inner}
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="Games Over Time">
          <ResponsiveContainer width="100%" height={200}>
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

        <ChartCard title="Unique Players Over Time">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={playersData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
              <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
              <YAxis {...CHART_STYLE.axis} />
              <Tooltip {...CHART_STYLE.tooltip} />
              <Line dataKey="combined" name="Unique Players" stroke="rgba(168,130,255,0.8)" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="New Player Acquisition">
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

        <ChartCard title="Avg Games per Player per Week">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={avgGppData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
              <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
              <YAxis {...CHART_STYLE.axis} />
              <Tooltip {...CHART_STYLE.tooltip} />
              <Line dataKey="avg" name="Avg Games/Player" stroke="rgba(219,154,4,0.8)" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard title="Top Player Dominance">
        <DominancePanel dom={dominance} />
      </ChartCard>

      <div className="bg-bg-raised border border-border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-1">Peak Activity Hours</h3>
        <p className="text-xs text-text-muted mb-3">Matches by day of week and hour (all time, EST)</p>
        <Heatmap data={heatmap} />
      </div>
    </section>
  )
}
