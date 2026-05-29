import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'

const CHART_STYLE = {
  grid: { stroke: 'rgba(255,255,255,0.05)' },
  axis: { tick: { fill: 'rgba(255,255,255,0.4)', fontSize: 10 }, tickLine: false, axisLine: false },
  tooltip: { contentStyle: { background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, fontSize: 11 } },
}

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

function parseUA(ua) {
  if (!ua) return 'Unknown'
  if (ua.includes('Edg/')) return 'Edge'
  if (ua.includes('OPR/') || ua.includes('Opera')) return 'Opera'
  if (ua.includes('Chrome/') && !ua.includes('Edg/')) return 'Chrome'
  if (ua.includes('Safari/') && !ua.includes('Chrome')) return 'Safari'
  if (ua.includes('Firefox/')) return 'Firefox'
  return 'Other'
}

function formatDate(ts) {
  if (!ts) return '--'
  try {
    return new Date(ts + 'Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch { return ts }
}

function timeAgo(ts) {
  if (!ts) return '--'
  const diff = (Date.now() - new Date(ts + 'Z').getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function UniqueUsers() {
  usePageTitle('Unique Users')
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    get('/api/analytics/unique-visitors')
      .then(d => { if (d.success) setStats(d) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (!stats) return <p className="text-text-muted text-center py-12">Failed to load data.</p>

  const maxDaily = Math.max(1, ...stats.daily_new.map(d => d.count))
  const maxWeekly = Math.max(1, ...stats.weekly_new.map(d => d.count))

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/admin/audit-log" className="text-text-muted hover:text-secondary transition-colors text-sm">&larr; Admin</Link>
        <div>
          <h1 className="text-2xl font-display text-secondary">Unique Users</h1>
          <p className="text-sm text-text-muted">IP-based unique visitor tracking</p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{stats.total.toLocaleString()}</div>
          <div className="text-xs text-text-muted mt-1">All Time</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-green-400">{stats.today}</div>
          <div className="text-xs text-text-muted mt-1">New Today</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{stats.this_week}</div>
          <div className="text-xs text-text-muted mt-1">This Week</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{stats.this_month}</div>
          <div className="text-xs text-text-muted mt-1">This Month</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{stats.returning}</div>
          <div className="text-xs text-text-muted mt-1">Returning</div>
        </div>
      </div>

      {/* Daily new visitors chart (last 30 days) */}
      {stats.daily_new.length > 0 && (
        <div className="bg-bg-raised border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">New Visitors Per Day (Last 30 Days)</h3>
          <div className="flex items-end gap-[2px] h-32">
            {stats.daily_new.map(d => (
              <div key={d.date} className="flex-1 flex flex-col items-center justify-end h-full group relative">
                <div
                  className="w-full bg-secondary/70 rounded-t hover:bg-secondary transition-colors min-h-[2px]"
                  style={{ height: `${(d.count / maxDaily) * 100}%` }}
                />
                <div className="absolute -top-8 bg-bg-surface border border-border rounded px-2 py-1 text-[10px] hidden group-hover:block whitespace-nowrap z-10">
                  {d.date}: {d.count}
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-between text-[10px] text-text-muted mt-1">
            <span>{stats.daily_new[0]?.date}</span>
            <span>{stats.daily_new[stats.daily_new.length - 1]?.date}</span>
          </div>
        </div>
      )}

      {/* Weekly new visitors chart */}
      {stats.weekly_new.length > 0 && (
        <div className="bg-bg-raised border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">New Visitors Per Week (All Time)</h3>
          <div className="flex items-end gap-[2px] h-32">
            {stats.weekly_new.map(d => (
              <div key={d.week} className="flex-1 flex flex-col items-center justify-end h-full group relative">
                <div
                  className="w-full bg-purple-500/70 rounded-t hover:bg-purple-500 transition-colors min-h-[2px]"
                  style={{ height: `${(d.count / maxWeekly) * 100}%` }}
                />
                <div className="absolute -top-8 bg-bg-surface border border-border rounded px-2 py-1 text-[10px] hidden group-hover:block whitespace-nowrap z-10">
                  Week {d.week}: {d.count}
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-between text-[10px] text-text-muted mt-1">
            <span>{stats.weekly_new[0]?.week}</span>
            <span>{stats.weekly_new[stats.weekly_new.length - 1]?.week}</span>
          </div>
        </div>
      )}

      {/* Cumulative total users over time */}
      {stats.weekly_new.length > 0 && (() => {
        let cumulative = 0
        const cumulativeData = stats.weekly_new.map(d => {
          cumulative += d.count
          return { week: d.week, label: weekLabel(d.week), total: cumulative, new: d.count }
        })
        return (
          <div className="bg-bg-raised border border-border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">Total Users Over Time</h3>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={cumulativeData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.grid.stroke} />
                <XAxis dataKey="label" {...CHART_STYLE.axis} interval="preserveStartEnd" />
                <YAxis {...CHART_STYLE.axis} />
                <Tooltip
                  {...CHART_STYLE.tooltip}
                  formatter={(value, name) => [value.toLocaleString(), name === 'total' ? 'Total Users' : 'New This Week']}
                />
                <Area type="monotone" dataKey="total" stroke="rgba(168,130,255,0.9)" fill="rgba(168,130,255,0.15)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )
      })()}

      {/* Top visitors table */}
      {stats.top_visitors.length > 0 && (
        <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
          <div className="p-4 border-b border-border">
            <h3 className="text-sm font-semibold">Most Active Visitors</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-text-muted bg-bg-surface">
                  <th className="py-2 px-3 text-left">IP</th>
                  <th className="py-2 px-3 text-left">Visits</th>
                  <th className="py-2 px-3 text-left">First Seen</th>
                  <th className="py-2 px-3 text-left">Last Seen</th>
                  <th className="py-2 px-3 text-left">Browser</th>
                  <th className="py-2 px-3 text-left">Timezone</th>
                </tr>
              </thead>
              <tbody>
                {stats.top_visitors.map((v, i) => (
                  <tr key={i} className="border-b border-border/30 hover:bg-bg-surface/50 transition-colors">
                    <td className="py-2 px-3 font-mono">{v.ip}</td>
                    <td className="py-2 px-3 font-bold text-secondary">{v.visit_count.toLocaleString()}</td>
                    <td className="py-2 px-3 text-text-muted">{formatDate(v.first_seen)}</td>
                    <td className="py-2 px-3 text-text-muted">{timeAgo(v.last_seen)}</td>
                    <td className="py-2 px-3">{parseUA(v.user_agent)}</td>
                    <td className="py-2 px-3">{v.timezone?.replace(/_/g, ' ') || '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
