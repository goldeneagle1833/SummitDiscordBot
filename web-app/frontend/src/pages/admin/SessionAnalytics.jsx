import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, LineChart, Line, Legend,
} from 'recharts'

const FILTERS = [
  { label: 'All Time', hours: null },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
  { label: '30d', hours: 720 },
  { label: '90d', hours: 2160 },
]

const CHART_STYLE = {
  grid: { stroke: 'rgba(255,255,255,0.05)' },
  axis: { tick: { fill: 'rgba(255,255,255,0.4)', fontSize: 10 }, tickLine: false, axisLine: false },
  tooltip: { contentStyle: { background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, fontSize: 11 } },
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0s'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function parseUA(ua) {
  if (!ua) return 'Unknown'
  if (ua.includes('Edg/')) return 'Edge'
  if (ua.includes('OPR/') || ua.includes('Opera')) return 'Opera'
  if (ua.includes('Chrome/') && !ua.includes('Edg/')) return 'Chrome'
  if (ua.includes('Safari/') && !ua.includes('Chrome')) return 'Safari'
  if (ua.includes('Firefox/')) return 'Firefox'
  return 'Other'
}

function formatTime(ts) {
  if (!ts) return '--'
  try {
    return new Date(ts + 'Z').toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    })
  } catch { return ts }
}

function cleanReferrer(ref) {
  if (!ref) return '--'
  try {
    const url = new URL(ref)
    // Show domain + path for external, just path for internal
    if (url.hostname.includes('sorcererssummit.com')) return url.pathname || '/'
    return url.hostname + (url.pathname !== '/' ? url.pathname : '')
  } catch {
    return ref
  }
}

export default function SessionAnalytics() {
  usePageTitle('Session Analytics')
  const [data, setData] = useState(null)
  const [hours, setHours] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedJourney, setExpandedJourney] = useState(null)

  const load = useCallback((h) => {
    setLoading(true)
    const url = h != null ? `/api/analytics/session-analytics?hours=${h}` : '/api/analytics/session-analytics'
    get(url)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(null) }, [load])

  const handleFilter = (h) => {
    setHours(h)
    load(h)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/admin/audit-log" className="text-text-muted hover:text-secondary transition-colors text-sm">&larr; Admin</Link>
        <div>
          <h1 className="text-2xl font-display text-secondary">Session Analytics</h1>
          <p className="text-sm text-text-muted">User journeys, bounce rate, session duration, and referrers</p>
        </div>
      </div>

      {/* Time filters */}
      <div className="flex gap-2 flex-wrap">
        {FILTERS.map(f => (
          <button
            key={f.label}
            onClick={() => handleFilter(f.hours)}
            className={`px-3 py-1 text-xs rounded border transition-colors ${
              hours === f.hours
                ? 'bg-secondary text-black border-secondary'
                : 'bg-bg-raised border-border text-text-muted hover:border-secondary'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? <Spinner className="py-12" /> : !data?.success ? (
        <p className="text-text-muted text-sm">Session analytics unavailable. Data will appear after sessions complete (users leave the site).</p>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-secondary">{(data.total_sessions || 0).toLocaleString()}</div>
              <div className="text-xs text-text-muted mt-1">Total Sessions</div>
            </div>
            <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              <div className={`text-2xl font-bold ${data.bounce_rate > 50 ? 'text-red-400' : data.bounce_rate > 30 ? 'text-yellow-400' : 'text-green-400'}`}>
                {data.bounce_rate}%
              </div>
              <div className="text-xs text-text-muted mt-1">Bounce Rate</div>
            </div>
            <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-secondary">{formatDuration(data.avg_duration)}</div>
              <div className="text-xs text-text-muted mt-1">Avg Duration</div>
            </div>
            <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-secondary">{data.avg_pages}</div>
              <div className="text-xs text-text-muted mt-1">Avg Pages/Session</div>
            </div>
          </div>

          {/* Daily sessions chart */}
          {data.daily?.length > 0 && (
            <div className="bg-bg-raised border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Sessions Per Day</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={[...data.daily].reverse()}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
                  <XAxis dataKey="date" {...CHART_STYLE.axis} interval="preserveStartEnd" />
                  <YAxis {...CHART_STYLE.axis} />
                  <Tooltip {...CHART_STYLE.tooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="sessions" name="Sessions" fill="rgba(77,184,255,0.7)" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Bounce rate + avg duration over time */}
          {data.daily?.length > 0 && (
            <div className="bg-bg-raised border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Bounce Rate & Avg Duration Over Time</h3>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={[...data.daily].reverse()}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
                  <XAxis dataKey="date" {...CHART_STYLE.axis} interval="preserveStartEnd" />
                  <YAxis yAxisId="left" {...CHART_STYLE.axis} unit="%" />
                  <YAxis yAxisId="right" orientation="right" {...CHART_STYLE.axis} unit="s" />
                  <Tooltip {...CHART_STYLE.tooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line yAxisId="left" dataKey="bounce_rate" name="Bounce %" stroke="rgba(255,99,71,0.8)" dot={false} strokeWidth={2} />
                  <Line yAxisId="right" dataKey="avg_duration" name="Avg Duration (s)" stroke="rgba(77,184,255,0.8)" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Top Referrers */}
            <div className="bg-bg-raised border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Top Referrers</h3>
              {data.top_referrers?.length > 0 ? (
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {data.top_referrers.map((r, i) => (
                    <div key={i} className="flex justify-between text-xs gap-2">
                      <span className="truncate font-mono" title={r.referrer}>{cleanReferrer(r.referrer)}</span>
                      <span className="text-text-muted shrink-0">{r.count}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="text-text-muted text-xs">No referrer data yet.</p>}
            </div>

            {/* Entry Pages */}
            <div className="bg-bg-raised border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Top Entry Pages</h3>
              {data.entry_pages?.length > 0 ? (
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {data.entry_pages.map((p, i) => (
                    <div key={i} className="flex justify-between text-xs gap-2">
                      <span className="truncate font-mono">{p.path}</span>
                      <span className="text-text-muted shrink-0">{p.count}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="text-text-muted text-xs">No data yet.</p>}
            </div>

            {/* Exit Pages */}
            <div className="bg-bg-raised border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Top Exit Pages</h3>
              {data.exit_pages?.length > 0 ? (
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {data.exit_pages.map((p, i) => (
                    <div key={i} className="flex justify-between text-xs gap-2">
                      <span className="truncate font-mono">{p.path}</span>
                      <span className="text-text-muted shrink-0">{p.count}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="text-text-muted text-xs">No data yet.</p>}
            </div>
          </div>

          {/* Logged-in Users */}
          {data.logged_in_users?.length > 0 && (
            <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-border">
                <h3 className="text-sm font-semibold">Logged-in User Activity</h3>
                <p className="text-xs text-text-muted">Which community members browse the site most</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-text-muted bg-bg-surface">
                      <th className="py-2 px-3 text-left">User</th>
                      <th className="py-2 px-3 text-right">Sessions</th>
                      <th className="py-2 px-3 text-right">Total Pages</th>
                      <th className="py-2 px-3 text-right">Avg Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.logged_in_users.map((u, i) => (
                      <tr key={i} className="border-b border-border/30 hover:bg-bg-surface/50 transition-colors">
                        <td className="py-2 px-3 font-semibold">{u.username || u.user_id}</td>
                        <td className="py-2 px-3 text-right text-secondary">{u.sessions}</td>
                        <td className="py-2 px-3 text-right">{u.total_pages}</td>
                        <td className="py-2 px-3 text-right text-text-muted">{formatDuration(u.avg_duration)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* User Journeys */}
          {data.journeys?.length > 0 && (
            <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-border">
                <h3 className="text-sm font-semibold">Recent User Journeys</h3>
                <p className="text-xs text-text-muted">Click a session to see the full page sequence</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-text-muted bg-bg-surface">
                      <th className="py-2 px-3 text-left">Session</th>
                      <th className="py-2 px-3 text-left">User</th>
                      <th className="py-2 px-3 text-left">When</th>
                      <th className="py-2 px-3 text-right">Pages</th>
                      <th className="py-2 px-3 text-right">Duration</th>
                      <th className="py-2 px-3 text-left">Browser</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.journeys.map((j, i) => (
                      <>
                        <tr
                          key={i}
                          onClick={() => setExpandedJourney(expandedJourney === i ? null : i)}
                          className="border-b border-border/30 hover:bg-bg-surface/50 transition-colors cursor-pointer"
                        >
                          <td className="py-2 px-3 font-mono text-text-muted">{j.session_id}</td>
                          <td className="py-2 px-3">
                            {j.username ? (
                              <span className="text-secondary font-semibold">{j.username}</span>
                            ) : (
                              <span className="text-text-muted">anonymous</span>
                            )}
                          </td>
                          <td className="py-2 px-3 whitespace-nowrap">{formatTime(j.first_seen)}</td>
                          <td className="py-2 px-3 text-right font-bold text-secondary">{j.page_count}</td>
                          <td className="py-2 px-3 text-right">{formatDuration(j.duration_seconds)}</td>
                          <td className="py-2 px-3">{parseUA(j.user_agent)}</td>
                        </tr>
                        {expandedJourney === i && j.pages?.length > 0 && (
                          <tr key={`${i}-pages`}>
                            <td colSpan={6} className="py-0 px-3 bg-bg-surface/30">
                              <div className="py-3 pl-4 border-l-2 border-secondary/30 ml-2">
                                {j.pages.map((p, pi) => (
                                  <div key={pi} className="flex items-center gap-2 py-0.5">
                                    <span className="text-[10px] text-text-muted w-5 text-right shrink-0">{pi + 1}.</span>
                                    <span className="w-1.5 h-1.5 rounded-full bg-secondary/50 shrink-0" />
                                    <span className="font-mono text-xs">{p.path}</span>
                                    <span className="text-[10px] text-text-muted">
                                      {p.time ? new Date(p.time + 'Z').toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : ''}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {data.total_sessions === 0 && (
            <div className="bg-bg-raised border border-border rounded-lg p-8 text-center">
              <p className="text-text-muted">No completed sessions yet. Data appears after users visit and leave the site.</p>
              <p className="text-xs text-text-muted mt-2">Sessions are recorded when a user's heartbeat stops for 2+ minutes.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
