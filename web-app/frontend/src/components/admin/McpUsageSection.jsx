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

function formatMs(ms) {
  if (ms == null) return '-'
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

const fmt = (n) => (n ?? 0).toLocaleString()

/** Admin: how AI apps use the Summit MCP server (sorcererssummit.com/mcp and /mcp/account). */
export default function McpUsageSection() {
  const [days, setDays] = useState(7)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    get(`/api/admin/mcp-usage?days=${days}`)
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
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <Tile label="Tool calls" value={fmt(t.calls)} />
            <Tile label="Signed-in players" value={fmt(t.players)} color="text-sky-400" />
            <Tile label="Public visitors" value={fmt(t.visitors)} />
            <Tile label="Errors" value={fmt(t.error)} color={t.error ? 'text-red-400' : 'text-secondary'} />
            <Tile label="Rate limited" value={fmt(t.limited)} color={t.limited ? 'text-amber-400' : 'text-secondary'} />
          </div>
          <p className="text-xs text-text-muted">
            <span className="text-secondary">{fmt(t.public)} public</span>
            {' · '}
            <span className="text-sky-400">{fmt(t.account)} signed in</span>
            {' · '}{fmt(t.no_result)} not found / bad input
            {t.signin ? <> · {fmt(t.signin)} expired {t.signin === 1 ? 'sign-in' : 'sign-ins'}</> : null}
            {' · '}last call {formatWhen(t.last_seen)}
          </p>

          {days > 1 && (
            <div>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 mb-2">
                <h3 className="text-sm font-semibold">Calls per day (UTC)</h3>
                <div className="flex gap-3 text-[11px] text-text-muted">
                  <span><span className="inline-block w-2 h-2 rounded-sm bg-secondary/80 mr-1" />Public</span>
                  <span><span className="inline-block w-2 h-2 rounded-sm bg-sky-400/80 mr-1" />Signed in</span>
                </div>
              </div>
              <div className="flex items-end gap-0.5 h-28 bg-bg-raised border border-border rounded-lg p-2" aria-label="Calls per day">
                {data.by_day.map((d) => (
                  <div
                    key={d.day}
                    className="flex-1 flex flex-col justify-end h-full min-w-0"
                    title={`${d.day}: ${fmt(d.calls)} calls (${fmt(d.public)} public, ${fmt(d.account)} signed in by ${fmt(d.players)} ${d.players === 1 ? 'player' : 'players'})${d.error ? `, ${fmt(d.error)} errors` : ''}`}
                  >
                    <div className="bg-sky-400/80 rounded-t-sm" style={{ height: `${(d.account / maxDay) * 100}%` }} />
                    <div className="bg-secondary/80" style={{ height: `${(d.public / maxDay) * 100}%` }} />
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
            <h3 className="text-sm font-semibold mb-2">By tool</h3>
            {data.by_tool.length === 0 ? (
              <p className="text-sm text-text-muted">No AI app calls in this range.</p>
            ) : (
              <ul className="space-y-2">
                {data.by_tool.map((x) => (
                  <li key={x.tool} className="bg-bg-raised border border-border rounded-lg p-3 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <span className="font-mono break-all">{x.tool}</span>
                      <span className="font-bold text-secondary">{fmt(x.calls)} {x.calls === 1 ? 'call' : 'calls'}</span>
                    </div>
                    <div className="text-xs text-text-muted mt-1">
                      {x.public ? <span className="text-secondary">{fmt(x.public)} public ({fmt(x.visitors)} {x.visitors === 1 ? 'visitor' : 'visitors'})</span> : null}
                      {x.public && x.account ? ' · ' : null}
                      {x.account ? <span className="text-sky-400">{fmt(x.account)} signed in ({fmt(x.players)} {x.players === 1 ? 'player' : 'players'})</span> : null}
                      {x.avg_ms != null && <> · avg {formatMs(x.avg_ms)}</>}
                      {x.no_result ? <> · {fmt(x.no_result)} not found</> : null}
                      {x.error ? <span className="text-red-400"> · {fmt(x.error)} {x.error === 1 ? 'error' : 'errors'}</span> : null}
                      {x.signin ? <span className="text-amber-400"> · {fmt(x.signin)} expired {x.signin === 1 ? 'sign-in' : 'sign-ins'}</span> : null}
                      {' · '}last call {formatWhen(x.last_seen)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-xs text-text-muted">
            Every tool call AI apps make through the Summit connectors: Public (sorcererssummit.com/mcp, no login) and
            Signed in (/mcp/account). Players and visitors are counted from a one-way code, so no names, player ids or
            IP addresses are stored. "Not found" is a normal answer (unknown player, card or Avatar); errors mean the
            site couldn't answer. Each visitor can make 60 calls a minute. Usage is kept for {data.retention_days} days.
          </p>
        </>
      )}
    </section>
  )
}
