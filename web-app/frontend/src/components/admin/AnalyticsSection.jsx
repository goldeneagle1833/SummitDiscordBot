import { useState, useEffect, useMemo } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LabelList,
} from 'recharts'

const TOOLTIP_STYLE = {
  contentStyle: { background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, fontSize: 11 },
}

const AXIS_TICK = { fill: 'rgba(255,255,255,0.4)', fontSize: 10 }

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

/** Narrowest bar (px) that still carries a readable value label. */
export const MIN_LABEL_BAR_WIDTH = 22

/** Value above a bar; dropped once bars get too thin to fit it. */
export function BarValueLabel({ x, y, width, value }) {
  if (width < MIN_LABEL_BAR_WIDTH) return null
  return (
    <text x={x + width / 2} y={y - 4} textAnchor="middle" fill="rgba(255,255,255,0.75)" fontSize={10}>
      {value}
    </text>
  )
}

/** Daily visitors for the last `days` days (null = all time). Bars shrink to fit the width. */
export function DailyActiveUsersChart({ daily, days }) {
  const rows = useMemo(() => dailyActiveRange(daily, days), [daily, days])

  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-1">Active Users (Daily)</h3>
      <p className="text-xs text-text-muted mb-3">
        Visitors = distinct browser sessions that viewed a page that day (UTC).
      </p>
      {rows.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={rows} margin={{ top: 20, right: 8, left: 0, bottom: 0 }} barCategoryGap="12%">
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip {...TOOLTIP_STYLE} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            <Bar dataKey="visitors" name="Visitors" fill="rgba(77,184,255,0.7)" radius={[2, 2, 0, 0]}>
              <LabelList dataKey="visitors" content={BarValueLabel} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
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

/** Today / 7-day / 30-day DAU tiles (fixed windows, independent of the range filter). */
export function ActiveUsersTiles({ activeUsers }) {
  if (!activeUsers) return null
  return (
    <>
      <ActiveUsersTile label="Visitors today" testId="dau-today" {...activeUsers.today} />
      <ActiveUsersTile label="7-day avg" testId="dau-7d" {...activeUsers.avg_7d} />
      <ActiveUsersTile label="30-day avg" testId="dau-30d" {...activeUsers.avg_30d} />
    </>
  )
}

/** Page views, banner clicks and top pages for the last `days` days (null = all time). */
export function PageViewsPanel({ days }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    get(days != null ? `/api/analytics/stats?hours=${days * 24}` : '/api/analytics/stats')
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [days])

  if (loading) return <Spinner className="py-8" />
  if (!data?.success) return <p className="text-text-muted text-sm">Analytics unavailable.</p>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{data.page_views.total.toLocaleString()}</div>
          <div className="text-xs text-text-muted mt-1">Page Views</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-secondary">{data.banner_clicks.total.toLocaleString()}</div>
          <div className="text-xs text-text-muted mt-1">Banner Clicks (all time)</div>
        </div>
        <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-green-400">
            {(data.banner_clicks.by_type?.find(b => b.banner_type === 'tcgplayer_buy')?.count || 0).toLocaleString()}
          </div>
          <div className="text-xs text-text-muted mt-1">TCGPlayer Clicks (all time)</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-bg-raised border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Page Views (Daily)</h3>
          {data.page_views.daily?.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={[...data.page_views.daily].reverse()}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} />
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
    </div>
  )
}
