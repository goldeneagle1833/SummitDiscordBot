import { useState, useEffect } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { parseServerTime } from '@/components/admin/DataExportsSection'

const RANGES = [
  { days: 1, label: 'Today' },
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
]

function Tile({ label, value, color = 'text-secondary' }) {
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value ?? '--'}</div>
      <div className="text-xs text-text-muted mt-1 leading-tight">{label}</div>
    </div>
  )
}

function formatWhen(value) {
  if (!value) return '-'
  const d = parseServerTime(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

const fmt = (n) => (n ?? 0).toLocaleString()

/** Admin: calls to the open APIs (match history, player search, Staples). */
export default function ApiUsageSection() {
  const [days, setDays] = useState(7)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    get(`/api/admin/api-usage?days=${days}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [days])

  const t = data?.totals
  const maxDay = Math.max(1, ...(data?.by_day ?? []).map((d) => d.calls))

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Time range">
        {RANGES.map((r) => (
          <button
            key={r.days}
            type="button"
            onClick={() => setDays(r.days)}
            aria-pressed={days === r.days}
            className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
              days === r.days ? 'border-secondary text-secondary bg-secondary/10' : 'border-border text-text-muted hover:text-text-primary'
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {loading && <Spinner />}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {!loading && !error && data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Tile label="API calls" value={fmt(t.calls)} />
            <Tile label="Callers (IPs)" value={fmt(t.callers)} />
            <Tile label="Rate limited (429)" value={fmt(t.limited)} color={t.limited ? 'text-amber-400' : 'text-secondary'} />
            <Tile label="Errors (500)" value={fmt(t.error)} color={t.error ? 'text-red-400' : 'text-secondary'} />
          </div>

          {days > 1 && (
            <div>
              <h3 className="text-sm font-semibold mb-2">Calls per day (UTC)</h3>
              <div className="flex items-end gap-0.5 h-28 bg-bg-raised border border-border rounded-lg p-2" aria-label="Calls per day">
                {data.by_day.map((d) => (
                  <div key={d.day} className="flex-1 flex flex-col justify-end h-full min-w-0" title={`${d.day}: ${fmt(d.calls)} calls${d.limited ? `, ${fmt(d.limited)} rate limited` : ''}`}>
                    <div className="bg-red-400/80 rounded-t-sm" style={{ height: `${(d.limited / maxDay) * 100}%` }} />
                    <div className="bg-secondary/80" style={{ height: `${((d.calls - d.limited) / maxDay) * 100}%` }} />
                  </div>
                ))}
              </div>
              <div className="flex justify-between text-[11px] text-text-muted mt-1">
                <span>{data.by_day[0]?.day}</span>
                <span>{data.by_day[data.by_day.length - 1]?.day}</span>
              </div>
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold mb-2">By API</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {data.by_endpoint.map((e) => (
                <div key={e.endpoint} className="bg-bg-raised border border-border rounded-lg p-3">
                  <div className="text-sm font-semibold">{e.endpoint}</div>
                  <div className="text-xl font-bold text-secondary">{fmt(e.calls)}</div>
                  <div className="text-xs text-text-muted">
                    {fmt(e.ok)} ok · {fmt(e.limited)} limited · {fmt(e.bad_request)} bad request · {fmt(e.error)} errors
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold mb-2">Top callers</h3>
            {data.top_callers.length === 0 ? (
              <p className="text-sm text-text-muted">No calls in this range.</p>
            ) : (
              <ul className="space-y-2">
                {data.top_callers.map((c) => (
                  <li key={c.ip} className="bg-bg-raised border border-border rounded-lg p-3 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <span className="font-mono break-all">{c.ip}</span>
                      <span className="font-bold text-secondary">{fmt(c.calls)} calls</span>
                    </div>
                    <div className="text-xs text-text-muted break-words mt-0.5">{c.user_agent || 'No app name sent'}</div>
                    <div className="text-xs text-text-muted mt-1">
                      {Object.entries(c.endpoints).map(([k, v]) => `${k} ${fmt(v)}`).join(' · ')}
                      {c.limited ? <span className="text-amber-400"> · {fmt(c.limited)} rate limited</span> : null}
                      {' · '}last call {formatWhen(c.last_seen)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-xs text-text-muted">
            Counts the open APIs only (no login or key): match history, player search and Staples. Each IP can make
            60 calls a minute. Usage is kept for {data.retention_days} days.
          </p>
        </>
      )}
    </section>
  )
}
