import { useMemo, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts'
import CollapsibleSection from './CollapsibleSection'
import { isHidden, isNum } from '@/utils/provisional'

const WIN_COLOR = 'rgba(63,185,80,0.95)'
const LOSS_COLOR = 'rgba(248,81,73,0.95)'
const LIFETIME_COLOR = 'rgba(77,184,255,0.85)'
const LEGACY_COLOR = 'rgba(200,160,90,0.85)'

export const LEGACY_LABEL = 'Legacy ELO (Seasons 1-8)'
export const LIFETIME_LABEL = 'Lifetime'

/**
 * Chart rows for the last `gameCount` points.
 *
 * Points carry an `era`: "legacy" (Elo lifetime, Seasons 1-8) or "glicko2"
 * (the Glicko-2 lifetime ladder, which restarted at 1500). Each era gets its
 * own series (`legacy` / `lifetime` keys, null outside it) so the restart
 * shows as a break between two lines, not a drop. `switchIndex` is the `idx`
 * of the first Glicko-2 point when the window holds both eras.
 */
export function buildEloChartData(points, gameCount) {
  const window = points.slice(-gameCount)
  const hasGlicko = window.some((m) => m.era === 'glicko2')
  const chartData = window.map((m, idx) => {
    const glicko = m.era === 'glicko2'
    return {
      idx,
      date: new Date(m.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      // Before the switch there is only one ladder: draw it as "lifetime"
      legacy: hasGlicko && !glicko ? m.elo_after : null,
      lifetime: !hasGlicko || glicko ? m.elo_after : null,
      era: glicko ? 'glicko2' : 'legacy',
      result: m.result,
      opponent: m.opponent,
      change: isHidden(m, 'elo_change') ? null : m.elo_change,
    }
  })
  const firstGlicko = chartData.findIndex((d) => d.era === 'glicko2')
  const switchIndex = hasGlicko && firstGlicko > 0 ? firstGlicko : null
  return { chartData, hasGlicko, hasLegacy: chartData.some((d) => d.legacy != null), switchIndex }
}

function GameDot(props) {
  const { cx, cy, payload } = props
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

function ActiveGameDot(props) {
  const { cx, cy, payload } = props
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

export default function EloHistory({ eloHistory, currentElo, open, onToggle }) {
  const validMatches = useMemo(
    () =>
      [...(eloHistory || [])]
        // Provisional (hidden) points come back null or flagged: skip them
        .filter((m) => isNum(m.elo_after) && !isHidden(m, 'elo_after') && m.date)
        .sort((a, b) => new Date(a.date) - new Date(b.date)),
    [eloHistory],
  )

  const maxGames = validMatches.length
  const [gameCount, setGameCount] = useState(() => Math.min(validMatches.length, 30))

  const { chartData, hasLegacy, switchIndex } = useMemo(
    () => buildEloChartData(validMatches, gameCount),
    [validMatches, gameCount],
  )

  if (!validMatches.length) return null

  const eloValues = chartData.map((d) => d.legacy ?? d.lifetime)
  const eloMin = Math.min(...eloValues)
  const eloMax = Math.max(...eloValues)
  const padding = Math.max(40, Math.round((eloMax - eloMin) * 0.2))

  const showDots = gameCount <= 60

  return (
    <CollapsibleSection title="ELO History" open={open} onToggle={onToggle}>
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4 mb-4 text-xs text-text-muted">
        <div className="flex items-center gap-2 flex-1 min-w-[160px]">
          <span className="whitespace-nowrap">Games: {gameCount}</span>
          <input
            type="range"
            min={Math.min(5, maxGames)}
            max={maxGames}
            step={1}
            value={gameCount}
            onChange={(e) => setGameCount(Number(e.target.value))}
            className="flex-1 accent-secondary"
          />
        </div>
      </div>

      {/* Chart */}
      <div style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="eloGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.4} />
                <stop offset="95%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="idx"
              type="number"
              domain={['dataMin', 'dataMax']}
              allowDecimals={false}
              tickFormatter={(idx) => chartData[idx]?.date ?? ''}
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
              formatter={(value, name, props) => {
                const change = props.payload?.change
                const suffix = change > 0 ? ` (+${change})` : change < 0 ? ` (${change})` : ''
                return [`${value}${suffix}`, name === 'legacy' ? 'Legacy ELO' : 'ELO']
              }}
              labelFormatter={(label, payload) => {
                if (payload?.[0]) {
                  const p = payload[0].payload
                  const resultColor = p.result === 'Win' ? '#3fb950' : '#f85149'
                  return (
                    <span>
                      <span style={{ color: resultColor }}>{p.result}</span>
                      {` vs ${p.opponent} · ${p.date}`}
                    </span>
                  )
                }
                return label
              }}
            />
            <ReferenceLine y={1500} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
            {switchIndex != null && (
              <ReferenceLine
                x={switchIndex - 0.5}
                stroke="rgba(255,255,255,0.35)"
                strokeDasharray="2 3"
                label={{ value: 'Glicko-2', position: 'insideTopRight', fill: 'rgba(255,255,255,0.5)', fontSize: 10 }}
              />
            )}
            {hasLegacy && (
              <Area
                type="monotone"
                dataKey="legacy"
                stroke={LEGACY_COLOR}
                fill="none"
                strokeWidth={2}
                connectNulls={false}
                dot={showDots ? <GameDot /> : false}
                activeDot={<ActiveGameDot />}
              />
            )}
            <Area
              type="monotone"
              dataKey="lifetime"
              stroke={LIFETIME_COLOR}
              fill="url(#eloGrad)"
              strokeWidth={2}
              connectNulls={false}
              dot={showDots ? <GameDot /> : false}
              activeDot={<ActiveGameDot />}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 mt-2 text-xs text-text-muted">
        {hasLegacy && (
          <>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-0.5" style={{ background: LEGACY_COLOR }} />
              {LEGACY_LABEL}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-0.5" style={{ background: LIFETIME_COLOR }} />
              {LIFETIME_LABEL} (Glicko-2, from 1500)
            </span>
          </>
        )}
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: WIN_COLOR }} />
          Win
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: LOSS_COLOR }} />
          Loss
        </span>
        {!showDots && (
          <span className="opacity-50">Nodes hidden above 60 games</span>
        )}
      </div>
    </CollapsibleSection>
  )
}
