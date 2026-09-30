import { useMemo, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts'
import CollapsibleSection from './CollapsibleSection'

// Avatar-mode seasons: each avatar has its own event ELO, so each gets its own graph
export default function AvatarEloHistory({ history, entries = [], eventName, open, onToggle }) {
  const avatars = useMemo(() => {
    const played = Object.keys(history || {})
    // Ladder order (best entry first), then anything else with history
    const ordered = entries.map((e) => e.avatar).filter((a) => played.includes(a))
    return [...ordered, ...played.filter((a) => !ordered.includes(a))]
  }, [history, entries])
  const [selected, setSelected] = useState(null)
  const avatar = avatars.includes(selected) ? selected : avatars[0]

  const chartData = useMemo(() => {
    const points = (history || {})[avatar] || []
    return [
      { game: 0, elo: 1500, date: 'Start' },
      ...points.map((p, i) => ({
        game: i + 1,
        elo: p.elo,
        date: p.timestamp
          ? new Date(p.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          : '',
      })),
    ]
  }, [history, avatar])

  if (!avatars.length) return null

  const values = chartData.map((d) => d.elo)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const padding = Math.max(30, Math.round((max - min) * 0.2))
  const entry = entries.find((e) => e.avatar === avatar)

  return (
    <CollapsibleSection title="Event ELO by Avatar" open={open} onToggle={onToggle}>
      <p className="text-xs text-text-muted mb-3">
        {eventName ? `${eventName}: ` : ''}every avatar is rated separately, starting at 1500.
      </p>
      <div className="flex flex-wrap gap-2 mb-4" role="tablist" aria-label="Avatar">
        {avatars.map((a) => (
          <button
            key={a}
            type="button"
            role="tab"
            aria-selected={a === avatar}
            onClick={() => setSelected(a)}
            className={`px-3 py-1 text-xs rounded border transition-colors ${
              a === avatar
                ? 'bg-secondary text-black border-secondary'
                : 'border-border text-text-muted hover:text-text-primary'
            }`}
          >
            {a}
          </button>
        ))}
      </div>
      {entry && (
        <p className="text-sm text-text-muted mb-2">
          {entry.event_elo} ELO · Rank #{entry.rank} · {entry.games_played} game{entry.games_played === 1 ? '' : 's'}
        </p>
      )}
      <div style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="game"
              tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              domain={[min - padding, max + padding]}
              tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={45}
            />
            <Tooltip
              contentStyle={{
                background: '#1a1a2e',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 4,
                fontSize: 11,
              }}
              formatter={(value) => [value, `${avatar} ELO`]}
              labelFormatter={(game, payload) => {
                const date = payload?.[0]?.payload?.date
                return game === 0 ? 'Start' : `Game ${game}${date ? ` · ${date}` : ''}`
              }}
            />
            <ReferenceLine y={1500} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="elo" stroke="rgba(77,184,255,0.85)" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </CollapsibleSection>
  )
}
