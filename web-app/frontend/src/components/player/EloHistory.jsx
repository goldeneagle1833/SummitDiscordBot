import { useEffect, useMemo, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts'
import CollapsibleSection from './CollapsibleSection'

const WIN_COLOR = 'rgba(63,185,80,0.95)'
const LOSS_COLOR = 'rgba(248,81,73,0.95)'

function GameDot({ cx, cy, payload }) {
  if (cx == null || cy == null) return null
  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill={payload.result === 'Win' ? WIN_COLOR : LOSS_COLOR}
      stroke="rgba(0,0,0,0.4)"
      strokeWidth={1}
    />
  )
}

function ActiveGameDot({ cx, cy, payload }) {
  if (cx == null || cy == null) return null
  return (
    <circle
      cx={cx}
      cy={cy}
      r={6}
      fill={payload.result === 'Win' ? WIN_COLOR : LOSS_COLOR}
      stroke="rgba(0,0,0,0.5)"
      strokeWidth={1.5}
    />
  )
}

function EloChart({ history, title, detail, gradientId }) {
  const validMatches = useMemo(
    () => [...(history || [])]
      .filter((match) => match.elo_after != null && match.date)
      .sort((a, b) => new Date(a.date) - new Date(b.date)),
    [history],
  )
  const maxGames = validMatches.length
  const [gameCount, setGameCount] = useState(() => Math.min(maxGames, 30))

  useEffect(() => {
    setGameCount((current) => Math.min(Math.max(current, Math.min(5, maxGames)), maxGames))
  }, [maxGames])

  const chartData = useMemo(() => {
    const window = validMatches.slice(-gameCount)
    return window.map((match) => ({
      date: new Date(match.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      elo: match.elo_after,
      result: match.result,
      opponent: match.opponent,
      change: match.elo_change,
    }))
  }, [validMatches, gameCount])

  if (!validMatches.length) {
    return (
      <div className="bg-bg-raised border border-border rounded-lg p-4">
        <h3 className="font-semibold text-text-primary">{title}</h3>
        {detail && <p className="text-xs text-text-muted mt-1">{detail}</p>}
        <p className="text-sm text-text-muted mt-4">No match history available.</p>
      </div>
    )
  }

  const eloValues = chartData.map((entry) => entry.elo)
  const eloMin = Math.min(...eloValues)
  const eloMax = Math.max(...eloValues)
  const padding = Math.max(40, Math.round((eloMax - eloMin) * 0.2))
  const showDots = gameCount <= 60

  return (
    <div className="bg-bg-raised border border-border rounded-lg p-4">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <h3 className="font-semibold text-text-primary">{title}</h3>
          {detail && <p className="text-xs text-text-muted mt-1">{detail}</p>}
        </div>
        <div className="flex items-center gap-2 text-xs text-text-muted min-w-[150px]">
          <span className="whitespace-nowrap">Games: {gameCount}</span>
          <input
            type="range"
            min={Math.min(5, maxGames)}
            max={maxGames}
            step={1}
            value={gameCount}
            onChange={(event) => setGameCount(Number(event.target.value))}
            className="flex-1 accent-secondary"
          />
        </div>
      </div>

      <div style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.4} />
                <stop offset="95%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="date"
              tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[eloMin - padding, eloMax + padding]}
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
              formatter={(value, _name, props) => {
                const change = props.payload?.change
                const suffix = change > 0 ? ` (+${change})` : change < 0 ? ` (${change})` : ''
                return [`${value}${suffix}`, 'ELO']
              }}
              labelFormatter={(label, payload) => {
                if (!payload?.[0]) return label
                const point = payload[0].payload
                const resultColor = point.result === 'Win' ? '#3fb950' : '#f85149'
                return (
                  <span>
                    <span style={{ color: resultColor }}>{point.result}</span>
                    {` vs ${point.opponent} · ${label}`}
                  </span>
                )
              }}
            />
            <ReferenceLine y={1500} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
            <Area
              type="monotone"
              dataKey="elo"
              stroke="rgba(77,184,255,0.85)"
              fill={`url(#${gradientId})`}
              strokeWidth={2}
              dot={showDots ? <GameDot /> : false}
              activeDot={<ActiveGameDot />}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center gap-4 mt-2 text-xs text-text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: WIN_COLOR }} />
          Win
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: LOSS_COLOR }} />
          Loss
        </span>
        {!showDots && <span className="opacity-50">Nodes hidden above 60 games</span>}
      </div>
    </div>
  )
}

export default function EloHistory({
  eloHistory,
  avatarEloHistories,
  avatarEvent,
  showLifetime,
  open,
  onToggle,
}) {
  const avatarSeries = avatarEloHistories || []
  const hasLifetime = showLifetime && (eloHistory || []).length > 0
  if (!hasLifetime && !avatarSeries.length) return null

  return (
    <CollapsibleSection title="ELO History" open={open} onToggle={onToggle}>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {hasLifetime && (
          <EloChart
            history={eloHistory}
            title="Lifetime ELO"
            gradientId="lifetimeEloGradient"
          />
        )}
        {avatarSeries.map((series, index) => (
          <EloChart
            key={series.avatar}
            history={series.history}
            title={series.avatar}
            detail={`${avatarEvent?.event_name || 'Event'} · ${series.current_elo} ELO${series.rank > 0 ? ` · Overall #${series.rank}` : ''}`}
            gradientId={`avatarEloGradient${index}`}
          />
        ))}
      </div>
    </CollapsibleSection>
  )
}
