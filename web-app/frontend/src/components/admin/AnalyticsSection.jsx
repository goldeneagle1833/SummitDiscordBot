import { useState, useEffect, useCallback, useMemo } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, LabelList,
} from 'recharts'

const FILTERS = [
  { label: 'All Time', hours: null },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
  { label: '30d', hours: 720 },
  { label: '90d', hours: 2160 },
]

const TOOLTIP_STYLE = {
  contentStyle: { background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, fontSize: 11 },
}

const AXIS_TICK = { fill: 'rgba(255,255,255,0.4)', fontSize: 10 }

const DAU_RANGES = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 60 days', days: 60 },
  { label: 'Last 90 days', days: 90 },
  { label: 'All Time', days: null },
]

const DAY_MS = 86400000

/** UTC "YYYY-MM-DD" for a Date, matching the server's date(timestamp) buckets. */
const isoDay = (d) => d.toISOString().slice(0, 10)

/**
 * One row per UTC day, oldest first, for the last `days` days (or from the
 * first recorded day when `days` is null). Days without traffic become zeros
 * so every day in the range gets a bar.
 */
export function dailyActiveRange(daily, days, now = new Date()) {
  if (!daily?.length) return []
  const byDay = Object.fromEntries(daily.map(d => [d.date, d]))
  const end = new Date(`${isoDay(now)}T00:00:00Z`)
  const earliest = daily.reduce((min, d) => (d.date < min ? d.date : min), daily[0].date)
  const start = days != null
    ? new Date(end.getTime() - (days - 1) * DAY_MS)
    : new Date(`${earliest}T00:00:00Z`)
  const rows = []
  for (let t = start.getTime(); t <= end.getTime(); t += DAY_MS) {
    const date = isoDay(new Date(t))
    rows.push({ date, visitors: byDay[date]?.visitors || 0, users: byDay[date]?.users || 0 })
  }
  return rows
}

const BAR_LABEL = { position: 'top', fill: 'rgba(255,255,255,0.75)', fontSize: 10 }

function DailyActiveUsersChart({ daily }) {
  const [days, setDays] = useState(30)
  const rows = useMemo(() => dailyActiveRange(daily, days), [daily, days])

  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="text-sm font-semibold">Active Users (Daily)</h3>
        <div className="flex gap-1 flex-wrap" role="group" aria-label="Date range">
          {DAU_RANGES.map(r => (
            <button
              key={r.label}
              type="button"
              onClick={() => setDays(r.days)}
              aria-pressed={days === r.days}
              className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                days === r.days
                  ? 'border-secondary text-secondary'
                  : 'border-border text-text-muted hover:text-text'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          {/* ~56px per day keeps both bars wide enough to carry a readable label;
              long ranges scroll sideways instead of squashing. */}
          <div style={{ minWidth: rows.length * 56 }}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={rows} margin={{ top: 20, right: 8, left: 0, bottom: 0 }} barCategoryGap="12%" barGap={2}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip {...TOOLTIP_STYLE} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="visitors" name="Visitors" fill="rgba(77,184,255,0.7)" radius={[2, 2, 0, 0]}>
                  <LabelList dataKey="visitors" {...BAR_LABEL} />
                </Bar>
                <Bar dataKey="users" name="Logged in" fill="rgba(74,222,128,0.8)" radius={[2, 2, 0, 0]}>
                  <LabelList dataKey="users" {...BAR_LABEL} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <p className="text-text-muted text-sm">No data yet.</p>
      )}
    </div>
  )
}

/** "4 visitors · 2 logged in" style tile for the DAU summary row. */
function ActiveUsersTile({ label, visitors, users, testId }) {
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4 text-center" data-testid={testId}>
      <div className="text-2xl font-bold text-secondary">{Number(visitors).toLocaleString()}</div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
      <div className="text-[11px] text-green-400 mt-0.5">{Number(users).toLocaleString()} logged in</div>
    </div>
  )
}

export default function AnalyticsSection() {
  const [data, setData] = useState(null)
  const [hours, setHours] = useState(null)
  const [loading, setLoading] = useState(true)
  // Active-user tiles and the daily chart use the all-time payload (from the
  // first, unfiltered load) and apply their own date range, so the page-view
  // filter below doesn't truncate them.
  const [activeUsers, setActiveUsers] = useState(null)

  const load = useCallback((h) => {
    setLoading(true)
    const url = h != null ? `/api/analytics/stats?hours=${h}` : '/api/analytics/stats'
    get(url)
      .then((d) => {
        setData(d)
        if (h == null && d?.success) setActiveUsers(d.active_users ?? null)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(null) }, [load])

  const handleFilter = (h) => {
    setHours(h)
    load(h)
  }

  return (
    <section className="space-y-4">
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

      {loading ? (
        <Spinner className="py-8" />
      ) : !data?.success ? (
        <p className="text-text-muted text-sm">Analytics unavailable.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-secondary">{data.page_views.total.toLocaleString()}</div>
              <div className="text-xs text-text-muted mt-1">Page Views</div>
            </div>
            <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-secondary">{data.banner_clicks.total.toLocaleString()}</div>
              <div className="text-xs text-text-muted mt-1">Banner Clicks</div>
            </div>
            <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-green-400">
                {(data.banner_clicks.by_type?.find(b => b.banner_type === 'tcgplayer_buy')?.count || 0).toLocaleString()}
              </div>
              <div className="text-xs text-text-muted mt-1">TCGPlayer Clicks</div>
            </div>
          </div>

          {activeUsers && (
            <div>
              <h3 className="text-sm font-semibold mb-2">Daily Active Users</h3>
              <p className="text-xs text-text-muted mb-3">
                Visitors = distinct browser sessions that viewed a page that day (UTC); logged in = distinct accounts.
              </p>
              <div className="grid grid-cols-3 gap-3">
                <ActiveUsersTile label="Today" testId="dau-today" {...activeUsers.today} />
                <ActiveUsersTile label="7-day avg" testId="dau-7d" {...activeUsers.avg_7d} />
                <ActiveUsersTile label="30-day avg" testId="dau-30d" {...activeUsers.avg_30d} />
              </div>
            </div>
          )}

          {activeUsers && <DailyActiveUsersChart daily={activeUsers.daily} />}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-bg-raised border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Page Views (Daily)</h3>
              {data.page_views.daily?.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={[...data.page_views.daily].reverse()}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip {...TOOLTIP_STYLE} />
                    <Bar dataKey="count" name="Page Views" fill="rgba(77,184,255,0.7)" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-text-muted text-sm">No data yet.</p>
              )}
            </div>

            <div className="bg-bg-raised border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Top Pages</h3>
              {data.page_views.top_pages?.length > 0 ? (
                <div className="overflow-y-auto max-h-52">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-text-muted">
                        <th className="py-1 px-2 text-left">Page</th>
                        <th className="py-1 px-2 text-right">Views</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.page_views.top_pages.map((p, i) => (
                        <tr key={i} className="border-b border-border/30">
                          <td className="py-1 px-2 font-mono">{p.path}</td>
                          <td className="py-1 px-2 text-right">{p.count.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-text-muted text-sm">No data yet.</p>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  )
}
