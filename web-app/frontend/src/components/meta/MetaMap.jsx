import { useState } from 'react'
import { Link } from 'react-router-dom'

/**
 * Meta map: every Avatar placed by share of decks (across) and win rate (up).
 * Shared by the Meta Report and the Avatars page. Data is always our own saved
 * totals; this component only draws it.
 */

export const ELEMENT_COLORS = { Earth: '#a07a4a', Fire: '#d9553a', Water: '#4d8fd6', Air: '#b3b6d4' }
export const TIER_COLORS = { S: '#ffd700', A: '#e6c200', B: '#a8bcf0', C: '#8b949e' }

const panel = 'bg-bg-surface border border-border rounded-lg p-4'

export function ElementPair({ pair }) {
  const parts = String(pair || '').split(' / ').filter(Boolean)
  return (
    <span className="text-xs">
      {parts.map((e, i) => (
        <span key={e}>
          {i > 0 && <span className="text-text-muted"> / </span>}
          <span style={{ color: ELEMENT_COLORS[e] || 'inherit' }}>{e}</span>
        </span>
      ))}
    </span>
  )
}

// Place labels most-played first and skip any that would collide, so a
// crowded corner shows dots (with hover titles) instead of a pile of text.
function placeLabels(points, width) {
  const placed = []
  const boxes = []
  const overlaps = (b) => boxes.some((o) => b.x1 < o.x2 && b.x2 > o.x1 && b.y1 < o.y2 && b.y2 > o.y1)
  const dots = points.map((p) => ({ x1: p.x - 7, x2: p.x + 7, y1: p.y - 7, y2: p.y + 7 }))
  ;[...points].sort((a, b) => b.games - a.games).forEach((p) => {
    const w = p.label.length * 6.2
    for (const side of p.x > width - 120 ? ['left', 'right'] : ['right', 'left']) {
      const x1 = side === 'right' ? p.x + 9 : p.x - 9 - w
      const box = { x1, x2: x1 + w, y1: p.y - 9, y2: p.y + 5 }
      const hitsDot = dots.some((d, i) => points[i] !== p && box.x1 < d.x2 && box.x2 > d.x1 && box.y1 < d.y2 && box.y2 > d.y1)
      if (!overlaps(box) && !hitsDot) {
        boxes.push(box)
        placed.push({ ...p, lx: side === 'right' ? p.x + 9 : p.x - 9, anchor: side === 'right' ? 'start' : 'end' })
        return
      }
    }
  })
  return placed
}

export default function MetaMap({ archetypes, linkAvatars = false, noun = 'deck' }) {
  const [picked, setPicked] = useState(null)
  if (!archetypes.length) return null
  const W = 460, H = 300, L = 40, R = 12, T = 14, B = 34
  const maxShare = Math.max(4, Math.ceil(Math.max(...archetypes.map((a) => a.share)) / 2) * 2)
  const wrs = archetypes.map((a) => a.winRate)
  const lo = Math.min(45, Math.floor(Math.min(...wrs) / 5) * 5)
  const hi = Math.max(55, Math.ceil(Math.max(...wrs) / 5) * 5)
  const X = (v) => L + (v / maxShare) * (W - L - R)
  const Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B)
  const step = (hi - lo) > 30 ? 10 : 5
  const yTicks = []
  for (let v = lo; v <= hi; v += step) yTicks.push(v)
  const xTicks = [0, maxShare / 4, maxShare / 2, (3 * maxShare) / 4, maxShare]
  const points = archetypes.map((a) => ({ ...a, x: X(a.share), y: Y(a.winRate), label: a.avatar }))
  const labels = placeLabels(points, W)
  return (
    <div className={panel}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block" role="img" aria-label="Archetypes by share of decks and win rate">
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="#30363d" />
            <text x={L - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="#8b949e">{v}%</text>
          </g>
        ))}
        {xTicks.map((v) => (
          <text key={v} x={X(v)} y={H - B + 16} textAnchor="middle" fontSize="11" fill="#8b949e">{Number.isInteger(v) ? v : v.toFixed(1)}%</text>
        ))}
        <line x1={L} x2={W - R} y1={Y(50)} y2={Y(50)} stroke="#8b949e" strokeDasharray="3 4" />
        <g fontSize="10" fill="#8b949e" opacity="0.8" style={{ letterSpacing: '0.06em' }}>
          <text x={L + 6} y={T + 12}>SLEEPERS</text>
          <text x={W - R - 6} y={T + 12} textAnchor="end">DECK TO BEAT</text>
          <text x={L + 6} y={H - B - 8}>STRUGGLING</text>
          <text x={W - R - 6} y={H - B - 8} textAnchor="end">OVERPLAYED</text>
        </g>
        <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="#8b949e">Share of decks</text>
        {points.map((a) => (
          <circle key={`${a.avatar}|${a.elements}`} cx={a.x} cy={a.y} r="5.5" fill={TIER_COLORS[a.tier]}
                  stroke={picked?.avatar === a.avatar && picked?.elements === a.elements ? '#f0f6fc' : '#0d1117'} strokeWidth="1.5" className="cursor-pointer"
                  onClick={() => setPicked(archetypes.find((x) => x.avatar === a.avatar && x.elements === a.elements))}>
            <title>{`${a.avatar}: ${a.share}% of decks, ${a.winRate}% win rate, ${a.games} games`}</title>
          </circle>
        ))}
        {labels.map((a) => (
          <text key={`l-${a.avatar}|${a.elements}`} x={a.lx} y={a.y + 4} textAnchor={a.anchor} fontSize="11" fill="#f0f6fc">{a.label}</text>
        ))}
      </svg>
      {picked ? (
        <p className="text-sm mt-1">
          {picked.avatar} <ElementPair pair={picked.elements} />{' '}
          <span className="text-text-muted">{picked.share}% of decks · {picked.winRate}% win rate · {picked.games} games · {picked.tier} tier</span>
          {linkAvatars && (
            <>
              {' '}
              <Link to={`/avatar/${encodeURIComponent(picked.avatar)}`} className="text-primary hover:underline">View Avatar</Link>
            </>
          )}
        </p>
      ) : labels.length < points.length && (
        <p className="text-xs text-text-muted mt-1">Labels show the most-played {noun}s. Tap a dot for any {noun}.</p>
      )}
    </div>
  )
}
