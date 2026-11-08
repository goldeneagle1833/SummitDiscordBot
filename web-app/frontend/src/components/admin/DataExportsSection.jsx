import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'

const RANGES = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
  { days: 3650, label: 'All time' },
]

export function formatBytes(n) {
  if (n == null) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// The server writes audit times in UTC without a zone; read them as UTC so
// they show in the viewer's own time.
export function parseServerTime(value) {
  if (!value) return new Date(NaN)
  const hasZone = /([zZ]|[+-]\d\d:?\d\d)$/.test(value)
  return new Date(hasZone ? value : `${value.replace(' ', 'T')}Z`)
}

function formatWhen(value) {
  if (!value) return '-'
  const d = parseServerTime(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function Tile({ label, value, color = 'text-secondary' }) {
  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value ?? '--'}</div>
      <div className="text-xs text-text-muted mt-1 leading-tight">{label}</div>
    </div>
  )
}

/** Admin: who has downloaded their "Export my data" zip, and how much. */
export default function DataExportsSection() {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    get(`/api/admin/data-exports?days=${days}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [days])

  const s = data?.summary
  const rangeLabel = RANGES.find((r) => r.days === days)?.label ?? `${days} days`
  const since = days >= 3650 ? null : Date.now() - days * 86400000
  const rows = (data?.entries ?? []).filter((e) => !since || parseServerTime(e.timestamp).getTime() >= since)

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

      {loading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : error ? (
        <div className="px-4 py-6 text-sm text-accent-red">{error}</div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Tile label={`Downloads (${rangeLabel})`} value={s.downloads} />
            <Tile label="Players" value={s.players} />
            <Tile label="Data downloaded" value={formatBytes(s.bytes)} />
            <Tile label="Failed" value={s.failed} color={s.failed ? 'text-accent-red' : 'text-text-muted'} />
          </div>

          {data.top_players?.some((p) => p.downloads > 1) && (
            <div className="text-xs text-text-muted">
              Most downloads:{' '}
              {data.top_players.filter((p) => p.downloads > 1).slice(0, 5).map((p, i) => (
                <span key={p.user_id}>
                  {i > 0 && ', '}
                  <Link to={`/player/${p.user_id}`} className="text-secondary hover:underline">{p.name}</Link>{' '}
                  ({p.downloads}x{p.bytes ? `, ${formatBytes(p.bytes)}` : ''})
                </span>
              ))}
            </div>
          )}

          <div className="bg-bg-raised border border-border rounded-lg overflow-hidden">
            {rows.length === 0 ? (
              <div className="px-4 py-6 text-sm text-text-muted">No data exports in this period.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-text-muted border-b border-border">
                      <th className="px-4 py-2 font-medium">Player</th>
                      <th className="px-4 py-2 font-medium whitespace-nowrap">When</th>
                      <th className="px-4 py-2 font-medium">Size</th>
                      <th className="px-4 py-2 font-medium">Matches</th>
                      <th className="px-4 py-2 font-medium">Sections</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e, i) => (
                      <tr key={`${e.timestamp}-${i}`} className="border-b border-border/50 last:border-b-0 align-top">
                        <td className="px-4 py-2">
                          <Link to={`/player/${e.user_id}`} className="text-text-primary hover:text-secondary">{e.name}</Link>
                          <div className="text-xs text-text-muted font-mono">{e.user_id}</div>
                        </td>
                        <td className="px-4 py-2 text-xs text-text-muted whitespace-nowrap">{formatWhen(e.timestamp)}</td>
                        <td className="px-4 py-2 whitespace-nowrap">
                          {e.ok ? formatBytes(e.bytes) : <span className="text-accent-red text-xs">Failed</span>}
                        </td>
                        <td className="px-4 py-2 text-text-muted">{e.matches ?? '-'}</td>
                        <td className="px-4 py-2 text-xs text-text-muted">{e.sections.length ? e.sections.join(', ') : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <p className="text-xs text-text-muted">
            {s.all_time_downloads} downloads all time. Every download and failed attempt is also in the Audit Log.
          </p>
        </>
      )}
    </section>
  )
}
