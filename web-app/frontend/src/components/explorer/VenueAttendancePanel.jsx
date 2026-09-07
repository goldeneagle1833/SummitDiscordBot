import { useState, useMemo } from 'react'
import { fetchVenueAttendance } from '@/api/explorer'
import Spinner from '@/components/ui/Spinner'

const TIER_COLORS = {
  Social: { bg: 'bg-blue-500', stroke: '#3b82f6', fill: 'rgba(59,130,246,0.3)' },
  Local: { bg: 'bg-green-500', stroke: '#22c55e', fill: 'rgba(34,197,94,0.3)' },
  Regional: { bg: 'bg-yellow-500', stroke: '#eab308', fill: 'rgba(234,179,8,0.3)' },
  National: { bg: 'bg-red-500', stroke: '#ef4444', fill: 'rgba(239,68,68,0.3)' },
}
const DEFAULT_TIER = { bg: 'bg-secondary', stroke: '#d4a843', fill: 'rgba(212,168,67,0.3)' }

const VIEW_OPTIONS = [
  { key: 'bar', label: 'Bar' },
  { key: 'line', label: 'Line' },
  { key: 'table', label: 'Table' },
]

// ── Bar Chart ─────────────────────────────────────────────────────────────

function AttendanceBar({ event, maxPlayers }) {
  const pct = maxPlayers > 0 ? (event.player_count / maxPlayers) * 100 : 0
  const barColor = (TIER_COLORS[event.tier] || DEFAULT_TIER).bg

  return (
    <div className="flex items-center gap-2 group relative">
      <div className="w-20 text-xs text-text-muted flex-shrink-0 text-right">{event.date || '—'}</div>
      <div className="flex-1 flex items-center gap-2">
        <div className="flex-1 bg-bg-elevated rounded-sm h-5 relative overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-sm transition-all duration-300`}
            style={{ width: `${Math.max(pct, 2)}%` }}
          />
        </div>
        <span className="w-6 text-xs text-text-primary font-medium text-right">{event.player_count}</span>
      </div>
      <div className="hidden group-hover:block absolute z-10 bg-bg-surface border border-border rounded px-2 py-1 text-xs text-text-primary shadow-lg left-24 -top-6 max-w-xs whitespace-nowrap pointer-events-none">
        {event.title} ({event.tier})
      </div>
    </div>
  )
}

function BarChartView({ events, maxPlayers }) {
  return (
    <div className="mt-3 space-y-0.5 max-h-96 overflow-y-auto pr-1">
      {events.map((event, i) => (
        <AttendanceBar key={`${event.date}-${i}`} event={event} maxPlayers={maxPlayers} />
      ))}
    </div>
  )
}

// ── Line Chart (SVG) ──────────────────────────────────────────────────────

function LineChartView({ events, maxPlayers }) {
  const W = 700
  const H = 200
  const PAD = { top: 15, right: 15, bottom: 30, left: 35 }
  const chartW = W - PAD.left - PAD.right
  const chartH = H - PAD.top - PAD.bottom

  const yMax = Math.ceil(maxPlayers * 1.1) || 10
  const yTicks = useMemo(() => {
    const step = Math.max(1, Math.ceil(yMax / 5))
    const ticks = []
    for (let v = 0; v <= yMax; v += step) ticks.push(v)
    return ticks
  }, [yMax])

  const points = events.map((ev, i) => ({
    x: PAD.left + (events.length > 1 ? (i / (events.length - 1)) * chartW : chartW / 2),
    y: PAD.top + chartH - (ev.player_count / yMax) * chartH,
    event: ev,
  }))

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const areaPath = linePath
    + ` L${points[points.length - 1].x},${PAD.top + chartH}`
    + ` L${points[0].x},${PAD.top + chartH} Z`

  // Show ~8 date labels max
  const labelStep = Math.max(1, Math.floor(events.length / 8))

  const [hovered, setHovered] = useState(null)

  return (
    <div className="mt-3 overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[500px]" preserveAspectRatio="xMidYMid meet">
        {/* Y grid + labels */}
        {yTicks.map(v => {
          const y = PAD.top + chartH - (v / yMax) * chartH
          return (
            <g key={v}>
              <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} stroke="currentColor" strokeOpacity={0.1} />
              <text x={PAD.left - 6} y={y + 3} textAnchor="end" className="fill-text-muted" fontSize={9}>{v}</text>
            </g>
          )
        })}

        {/* Area fill */}
        {points.length > 1 && <path d={areaPath} fill="rgba(212,168,67,0.15)" />}

        {/* Line */}
        {points.length > 1 && (
          <path d={linePath} fill="none" stroke="#d4a843" strokeWidth={2} strokeLinejoin="round" />
        )}

        {/* Data points */}
        {points.map((p, i) => {
          const tierColor = (TIER_COLORS[p.event.tier] || DEFAULT_TIER).stroke
          return (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={hovered === i ? 5 : 3}
              fill={tierColor}
              stroke="var(--color-bg-surface, #1a1a2e)"
              strokeWidth={1.5}
              className="cursor-pointer transition-all"
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
            />
          )
        })}

        {/* X-axis date labels */}
        {events.map((ev, i) => {
          if (i % labelStep !== 0 && i !== events.length - 1) return null
          const x = points[i].x
          return (
            <text key={i} x={x} y={H - 5} textAnchor="middle" className="fill-text-muted" fontSize={8}>
              {(ev.date || '').slice(5)}
            </text>
          )
        })}

        {/* Tooltip */}
        {hovered !== null && (
          <g>
            <rect
              x={Math.min(points[hovered].x - 60, W - 135)}
              y={Math.max(points[hovered].y - 38, 2)}
              width={120}
              height={30}
              rx={4}
              fill="var(--color-bg-surface, #1a1a2e)"
              stroke="var(--color-border, #333)"
              strokeWidth={1}
            />
            <text
              x={Math.min(points[hovered].x, W - 75)}
              y={Math.max(points[hovered].y - 22, 18)}
              textAnchor="middle"
              className="fill-text-primary"
              fontSize={9}
              fontWeight={600}
            >
              {events[hovered].title.slice(0, 22)}{events[hovered].title.length > 22 ? '...' : ''}
            </text>
            <text
              x={Math.min(points[hovered].x, W - 75)}
              y={Math.max(points[hovered].y - 11, 29)}
              textAnchor="middle"
              className="fill-text-muted"
              fontSize={8}
            >
              {events[hovered].date} — {events[hovered].player_count} players
            </text>
          </g>
        )}
      </svg>
    </div>
  )
}

// ── Table View ────────────────────────────────────────────────────────────

function TableView({ events }) {
  return (
    <div className="mt-3 max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-bg-surface">
          <tr className="border-b border-border text-xs text-text-muted">
            <th className="py-1.5 px-2 text-left">Date</th>
            <th className="py-1.5 px-2 text-left">Event</th>
            <th className="py-1.5 px-2 text-center">Players</th>
            <th className="py-1.5 px-2 text-center">Tier</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev, i) => (
            <tr key={`${ev.date}-${i}`} className="border-b border-border/30 hover:bg-white/5">
              <td className="py-1.5 px-2 text-text-muted text-xs">{ev.date || '—'}</td>
              <td className="py-1.5 px-2 text-text-primary text-xs truncate max-w-[250px]">{ev.title}</td>
              <td className="py-1.5 px-2 text-center text-text-primary font-medium text-xs">{ev.player_count}</td>
              <td className="py-1.5 px-2 text-center">
                <span className={`inline-block w-2.5 h-2.5 rounded-sm ${(TIER_COLORS[ev.tier] || DEFAULT_TIER).bg}`} title={ev.tier} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Shared ────────────────────────────────────────────────────────────────

function TierLegend() {
  return (
    <div className="flex gap-3 text-xs text-text-muted">
      {Object.entries(TIER_COLORS).map(([name, c]) => (
        <span key={name} className="flex items-center gap-1">
          <span className={`w-2.5 h-2.5 rounded-sm ${c.bg}`} />
          {name}
        </span>
      ))}
    </div>
  )
}

function ViewToggle({ view, setView }) {
  return (
    <div className="flex rounded border border-border overflow-hidden">
      {VIEW_OPTIONS.map(opt => (
        <button
          key={opt.key}
          onClick={() => setView(opt.key)}
          className={`px-2.5 py-1 text-xs transition-colors ${
            view === opt.key
              ? 'bg-secondary text-black font-medium'
              : 'bg-bg-elevated text-text-muted hover:text-text-primary'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────

export default function VenueAttendancePanel() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)
  const [view, setView] = useState('bar')

  const handleFetch = async (e) => {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const result = await fetchVenueAttendance(url.trim())
      setData(result)
    } catch (err) {
      setError(err.message || 'Failed to fetch venue attendance')
    } finally {
      setLoading(false)
    }
  }

  const maxPlayers = data ? Math.max(...data.events.map(e => e.player_count), 1) : 0
  const avgAttendance = data && data.events.length > 0
    ? (data.events.reduce((sum, e) => sum + e.player_count, 0) / data.events.length).toFixed(1)
    : 0
  const eventsWithPlayers = data ? data.events.filter(e => e.player_count > 0) : []
  const avgWithPlayers = eventsWithPlayers.length > 0
    ? (eventsWithPlayers.reduce((sum, e) => sum + e.player_count, 0) / eventsWithPlayers.length).toFixed(1)
    : 0

  return (
    <div>
      <form onSubmit={handleFetch} className="flex gap-2 mb-3">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://sorcerytcg.com/stores/..."
          className="flex-1 bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm text-text-primary placeholder-text-muted/50 focus:border-secondary focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !url.trim()}
          className="px-4 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-50"
        >
          {loading ? 'Fetching...' : 'Lookup'}
        </button>
      </form>

      {error && <p className="text-sm text-red-400 mb-3">{error}</p>}

      {loading && (
        <div className="flex items-center gap-2 text-sm text-text-muted py-4">
          <Spinner />
          <span>Fetching venue events and player counts... This may take a moment.</span>
        </div>
      )}

      {data && (
        <div>
          {/* Store info */}
          <div className="flex items-center justify-between mb-3">
            <div>
              <h4 className="text-base font-semibold text-text-primary">{data.store_name}</h4>
              <p className="text-xs text-text-muted">{data.address}</p>
            </div>
            <span className={`text-xs px-2 py-0.5 rounded border ${
              data.status === 'Approved'
                ? 'bg-green-500/10 text-green-400 border-green-500/30'
                : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30'
            }`}>
              {data.status}
            </span>
          </div>

          {/* Stats summary + view toggle */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div className="flex flex-wrap gap-4 text-xs text-text-muted">
              <span><span className="text-text-primary font-medium">{data.events.length}</span> total events</span>
              <span>Avg attendance: <span className="text-text-primary font-medium">{avgAttendance}</span></span>
              {eventsWithPlayers.length !== data.events.length && (
                <span>Avg (excl. zero): <span className="text-text-primary font-medium">{avgWithPlayers}</span></span>
              )}
              <span>Peak: <span className="text-text-primary font-medium">{maxPlayers}</span></span>
            </div>
            <ViewToggle view={view} setView={setView} />
          </div>

          <TierLegend />

          {/* Chart / table */}
          {data.events.length === 0 ? (
            <p className="text-sm text-text-muted py-4">No past events found for this venue.</p>
          ) : (
            <>
              {view === 'bar' && <BarChartView events={data.events} maxPlayers={maxPlayers} />}
              {view === 'line' && <LineChartView events={data.events} maxPlayers={maxPlayers} />}
              {view === 'table' && <TableView events={data.events} />}
            </>
          )}
        </div>
      )}
    </div>
  )
}
