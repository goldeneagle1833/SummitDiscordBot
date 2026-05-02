import { useState, useMemo } from 'react'

const CARD_TYPE_ORDER = ['Minion', 'Magic', 'Artifact', 'Aura', 'Site', 'Other']
const GROUP_BY_OPTIONS = [
  { value: 'type', label: 'Type' },
  { value: 'mana', label: 'Mana Cost' },
  { value: 'flat', label: 'All Cards' },
]

function getCardType(card) {
  const type = (card.type || '').toLowerCase()
  if (type.includes('minion')) return 'Minion'
  if (type.includes('magic')) return 'Magic'
  if (type.includes('artifact')) return 'Artifact'
  if (type.includes('aura')) return 'Aura'
  if (type.includes('site')) return 'Site'
  return 'Other'
}

function getManaCost(card) {
  return card.threshold || card.cost || card.mana || card.mana_cost || 0
}

function isSite(card) {
  return getCardType(card) === 'Site'
}

function buildGroups(cards, groupBy) {
  if (groupBy === 'flat') {
    const sorted = [...cards].sort((a, b) => getManaCost(a) - getManaCost(b) || (a.name || '').localeCompare(b.name || ''))
    return [{ key: 'all', label: `All Cards`, cards: sorted }]
  }

  if (groupBy === 'mana') {
    // Exclude sites from mana cost grouping
    const nonSites = cards.filter((c) => !isSite(c))
    const sites = cards.filter((c) => isSite(c))
    const buckets = {}
    nonSites.forEach((card) => {
      const cost = getManaCost(card)
      const key = String(cost)
      if (!buckets[key]) buckets[key] = []
      buckets[key].push(card)
    })
    const groups = Object.keys(buckets)
      .sort((a, b) => Number(a) - Number(b))
      .map((cost) => ({
        key: `mana-${cost}`,
        label: `Cost ${cost}`,
        cards: buckets[cost].sort((a, b) => (a.name || '').localeCompare(b.name || '')),
      }))
    // Append sites as their own group at the end
    if (sites.length) {
      groups.push({ key: 'sites', label: 'Atlas', cards: sites })
    }
    return groups
  }

  // Default: group by type
  const groups = {}
  CARD_TYPE_ORDER.forEach((t) => { groups[t] = [] })
  cards.forEach((card) => {
    const type = getCardType(card)
    if (!groups[type]) groups[type] = []
    groups[type].push(card)
  })
  for (const type of Object.keys(groups)) {
    groups[type].sort((a, b) => getManaCost(a) - getManaCost(b))
  }
  return CARD_TYPE_ORDER
    .filter((type) => groups[type]?.length)
    .map((type) => ({
      key: type,
      label: type === 'Site' ? 'Atlas' : type + 's',
      cards: groups[type],
    }))
}

/* ---- Donut Chart ---- */
function DonutChart({ segments, size = 64, strokeWidth = 10 }) {
  const r = (size - strokeWidth) / 2
  const cx = size / 2
  const cy = size / 2
  const circumference = 2 * Math.PI * r

  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {segments.map((seg) => {
        const dash = (seg.pct / 100) * circumference
        const gap = circumference - dash
        const currentOffset = offset
        offset += dash
        return (
          <circle
            key={seg.label}
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={seg.color}
            strokeWidth={strokeWidth}
            strokeDasharray={`${dash} ${gap}`}
            strokeDashoffset={-currentOffset}
            style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }}
          />
        )
      })}
    </svg>
  )
}

/* ---- Mana Curve Line Graph ---- */
function ManaCurveGraph({ entries, maxCount }) {
  const W = 280
  const H = 80
  const PAD_L = 20
  const PAD_R = 10
  const PAD_T = 16
  const PAD_B = 20
  const graphW = W - PAD_L - PAD_R
  const graphH = H - PAD_T - PAD_B

  if (!entries.length) return null

  const n = entries.length
  const xStep = n > 1 ? graphW / (n - 1) : 0

  const points = entries.map((e, i) => ({
    x: PAD_L + i * xStep,
    y: PAD_T + graphH - (maxCount > 0 ? (e.count / maxCount) * graphH : 0),
    cost: e.cost,
    count: e.count,
  }))

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const areaPath = linePath + ` L${points[points.length - 1].x},${PAD_T + graphH} L${points[0].x},${PAD_T + graphH} Z`

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-sm mt-1" preserveAspectRatio="xMidYMid meet">
      {/* Grid lines */}
      {[0, 0.5, 1].map((frac) => {
        const y = PAD_T + graphH * (1 - frac)
        return <line key={frac} x1={PAD_L} x2={W - PAD_R} y1={y} y2={y} stroke="currentColor" className="text-border" strokeWidth="0.5" />
      })}
      {/* Area fill */}
      <path d={areaPath} fill="currentColor" className="text-secondary/20" />
      {/* Line */}
      <path d={linePath} fill="none" stroke="currentColor" className="text-secondary" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {/* Dots + labels */}
      {points.map((p) => (
        <g key={p.cost}>
          <circle cx={p.x} cy={p.y} r="3" fill="currentColor" className="text-secondary" />
          <text x={p.x} y={p.y - 5} textAnchor="middle" className="fill-text-muted" style={{ fontSize: '8px' }}>{p.count}</text>
          <text x={p.x} y={PAD_T + graphH + 12} textAnchor="middle" className="fill-text-muted" style={{ fontSize: '8px' }}>{p.cost}</text>
        </g>
      ))}
    </svg>
  )
}

const TYPE_COLORS = {
  Minion: '#ef4444',   // red
  Magic: '#3b82f6',    // blue
  Artifact: '#a855f7', // purple
  Aura: '#eab308',     // yellow
  Site: '#22c55e',     // green
  Other: '#6b7280',    // gray
}

const ELEMENT_COLORS = {
  Earth: '#a16207',
  Fire: '#dc2626',
  Water: '#2563eb',
  Air: '#7dd3fc',
}

const RARITY_COLORS = {
  Ordinary: '#9ca3af',
  Exceptional: '#22c55e',
  Elite: '#3b82f6',
  Unique: '#eab308',
  Unknown: '#6b7280',
}

/* ---- Deck Stats ---- */
function DeckStatsBar({ cards, spellbookCards }) {
  const stats = useMemo(() => {
    if (!cards.length) return null

    const totalCards = cards.reduce((sum, c) => sum + (c.quantity || c.qty || 1), 0)

    // Per-type counts (weighted by quantity) — all cards
    const typeCounts = {}
    cards.forEach((card) => {
      const qty = card.quantity || card.qty || 1
      const type = getCardType(card)
      typeCounts[type] = (typeCounts[type] || 0) + qty
    })

    // Avg mana cost — spellbook only, excluding sites
    const sbCards = spellbookCards || cards
    const sbNonSites = sbCards.filter((c) => !isSite(c))
    let totalMana = 0
    let manaCards = 0
    sbNonSites.forEach((card) => {
      const qty = card.quantity || card.qty || 1
      const cost = getManaCost(card)
      totalMana += cost * qty
      manaCards += qty
    })

    const avgMana = manaCards > 0 ? (totalMana / manaCards).toFixed(2) : '—'
    const minions = typeCounts['Minion'] || 0
    const spells = (typeCounts['Magic'] || 0) + (typeCounts['Artifact'] || 0) + (typeCounts['Aura'] || 0)
    const sites = typeCounts['Site'] || 0

    // Type distribution for donut chart
    const typeSegments = CARD_TYPE_ORDER
      .filter((t) => typeCounts[t])
      .map((t) => ({
        label: t === 'Site' ? 'Atlas' : t + 's',
        count: typeCounts[t],
        pct: (typeCounts[t] / totalCards) * 100,
        color: TYPE_COLORS[t] || TYPE_COLORS.Other,
      }))

    // Element breakdown
    const elementCounts = {}
    let elementTotal = 0
    cards.forEach((card) => {
      const qty = card.quantity || card.qty || 1
      const els = card.elements || ''
      if (els && els !== 'None') {
        els.split(',').forEach((e) => {
          const el = e.trim()
          if (el) {
            elementCounts[el] = (elementCounts[el] || 0) + qty
            elementTotal += qty
          }
        })
      }
    })
    const elementSegments = ['Earth', 'Fire', 'Water', 'Air']
      .filter((el) => elementCounts[el])
      .map((el) => ({
        label: el,
        count: elementCounts[el],
        pct: elementTotal > 0 ? (elementCounts[el] / elementTotal) * 100 : 0,
        color: ELEMENT_COLORS[el],
      }))

    // Avg attack/defence of minions
    // All_Cards_Array uses attack/defence; Curiosa API uses power (combined stat)
    let totalAttack = 0, totalDefence = 0, minionStatCount = 0
    let totalPower = 0, powerCount = 0
    cards.forEach((card) => {
      if (getCardType(card) !== 'Minion') return
      const qty = card.quantity || card.qty || 1
      if (card.attack != null && card.defence != null) {
        totalAttack += card.attack * qty
        totalDefence += card.defence * qty
        minionStatCount += qty
      } else if (card.power != null) {
        totalPower += card.power * qty
        powerCount += qty
      }
    })
    const avgAttack = minionStatCount > 0 ? (totalAttack / minionStatCount).toFixed(1) : null
    const avgDefence = minionStatCount > 0 ? (totalDefence / minionStatCount).toFixed(1) : null
    const avgPower = powerCount > 0 ? (totalPower / powerCount).toFixed(1) : null

    // Rarity distribution
    const rarityCounts = {}
    cards.forEach((card) => {
      const qty = card.quantity || card.qty || 1
      const rarity = card.rarity || 'Unknown'
      rarityCounts[rarity] = (rarityCounts[rarity] || 0) + qty
    })
    const raritySegments = ['Ordinary', 'Exceptional', 'Elite', 'Unique']
      .filter((r) => rarityCounts[r])
      .map((r) => ({
        label: r,
        count: rarityCounts[r],
        pct: (rarityCounts[r] / totalCards) * 100,
        color: RARITY_COLORS[r],
      }))

    // Mana curve distribution — spellbook only, excluding sites
    const curve = {}
    sbNonSites.forEach((card) => {
      const cost = getManaCost(card)
      const qty = card.quantity || card.qty || 1
      curve[cost] = (curve[cost] || 0) + qty
    })
    // Fill gaps so line graph is continuous
    const costKeys = Object.keys(curve).map(Number)
    const minCost = Math.min(...costKeys)
    const maxCost = Math.max(...costKeys)
    for (let c = minCost; c <= maxCost; c++) {
      if (!(c in curve)) curve[c] = 0
    }
    const maxCurve = Math.max(...Object.values(curve), 1)
    const curveEntries = Object.keys(curve)
      .map(Number)
      .sort((a, b) => a - b)
      .map((cost) => ({ cost, count: curve[cost], pct: (curve[cost] / maxCurve) * 100 }))

    return {
      totalCards, avgMana, minions, spells, sites,
      typeSegments, elementSegments, raritySegments,
      avgAttack, avgDefence, avgPower,
      curveEntries, maxCurve,
    }
  }, [cards, spellbookCards])

  if (!stats) return null

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4 mb-4">
      <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Deck Stats</h4>

      {/* Main layout: left column (stats + mana curve), right column (donuts) */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Left side: stats numbers + mana curve */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-4">
            <div>
              <span className="text-text-muted">Cards: </span>
              <span className="text-text-primary font-medium">{stats.totalCards}</span>
            </div>
            <div>
              <span className="text-text-muted">Avg Mana Cost: </span>
              <span className="text-text-primary font-medium">{stats.avgMana}</span>
            </div>
            <div>
              <span className="text-text-muted">Spell:Minion: </span>
              <span className="text-text-primary font-medium">{stats.spells} : {stats.minions}</span>
            </div>
            {stats.avgAttack && (
              <div>
                <span className="text-text-muted">Avg Minion: </span>
                <span className="text-text-primary font-medium">{stats.avgAttack} / {stats.avgDefence}</span>
              </div>
            )}
            {!stats.avgAttack && stats.avgPower && (
              <div>
                <span className="text-text-muted">Avg Minion Power: </span>
                <span className="text-text-primary font-medium">{stats.avgPower}</span>
              </div>
            )}
          </div>

          {stats.curveEntries.length > 0 && (
            <div>
              <div className="text-xs text-text-muted font-semibold uppercase tracking-wider mb-1">Mana Curve</div>
              <ManaCurveGraph entries={stats.curveEntries} maxCount={stats.maxCurve} />
            </div>
          )}
        </div>

        {/* Right side: donuts — stretch full height */}
        <div className="flex flex-col justify-center gap-4">
          {/* Type Distribution */}
          {stats.typeSegments.length > 0 && (
            <div className="flex items-center gap-3">
              <div className="text-xs space-y-0.5">
                <div className="text-text-muted font-semibold uppercase tracking-wider mb-1">Types</div>
                {stats.typeSegments.map((s) => (
                  <div key={s.label} className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                    <span className="text-text-muted">{s.label}</span>
                    <span className="text-text-primary font-medium">{s.count}</span>
                  </div>
                ))}
              </div>
              <DonutChart segments={stats.typeSegments} />
            </div>
          )}

          {/* Element Breakdown */}
          {stats.elementSegments.length > 0 && (
            <div className="flex items-center gap-3">
              <div className="text-xs space-y-0.5">
                <div className="text-text-muted font-semibold uppercase tracking-wider mb-1">Elements</div>
                {stats.elementSegments.map((s) => (
                  <div key={s.label} className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                    <span className="text-text-muted">{s.label}</span>
                    <span className="text-text-primary font-medium">{s.count} ({Math.round(s.pct)}%)</span>
                  </div>
                ))}
              </div>
              <DonutChart segments={stats.elementSegments} />
            </div>
          )}

          {/* Rarity Distribution */}
          {stats.raritySegments.length > 0 && (
            <div className="flex items-center gap-3">
              <div className="text-xs space-y-0.5">
                <div className="text-text-muted font-semibold uppercase tracking-wider mb-1">Rarity</div>
                {stats.raritySegments.map((s) => (
                  <div key={s.label} className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                    <span className="text-text-muted">{s.label}</span>
                    <span className="text-text-primary font-medium">{s.count}</span>
                  </div>
                ))}
              </div>
              <DonutChart segments={stats.raritySegments} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * Shared Deck Visualizer - displays card images in a grid, grouped by type.
 *
 * Accepts cards in two formats:
 *   1. Snapshot format: { deck: { spellbook: [], atlas: [], sideboard: [] } }
 *      Pass `spellbook`, `atlas`, `sideboard` as separate props.
 *   2. Flat card list: pass `cards` prop directly.
 *
 * Each card object should have: name, image (filename), quantity/qty, type (optional).
 */
export default function DeckVisualizer({ cards, spellbook, atlas, sideboard }) {
  const [groupBy, setGroupBy] = useState('type')

  // Merge all sources into one list
  let allCards = []
  // Track which cards are spellbook-only (for stats calculation)
  let spellbookCards = []
  if (cards) {
    allCards = cards
    spellbookCards = cards
  } else {
    if (spellbook) {
      allCards.push(...spellbook)
      spellbookCards = spellbook
    }
    if (atlas) allCards.push(...atlas)
    if (sideboard) allCards.push(...sideboard)
  }

  const withImages = allCards.filter((c) => c.image)
  const groups = useMemo(() => buildGroups(withImages, groupBy), [withImages, groupBy])

  if (!withImages.length) {
    return (
      <div className="bg-bg-surface border border-border rounded-lg p-6 text-center">
        <p className="text-text-muted text-sm">Visual deck view coming soon. Card images not available for this deck.</p>
      </div>
    )
  }

  // Each copy is offset 15% of the card's height below the previous one.
  const GAP_PCT = 15
  const CARD_RATIO = 1.386 // Sorcery card height/width ratio (88mm / 63.5mm)
  const GAP_WIDTH_PCT = GAP_PCT * CARD_RATIO // ≈ 20.8% of width per step

  return (
    <div className="space-y-4">
      {/* Deck Stats — uses spellbook only for mana averages */}
      <DeckStatsBar cards={allCards} spellbookCards={spellbookCards} />

      {/* Group By Controls */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-text-muted">Group by:</span>
        <div className="inline-flex bg-bg-raised border border-border rounded-lg overflow-hidden">
          {GROUP_BY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setGroupBy(opt.value)}
              className={`px-3 py-1 text-xs font-medium transition-colors ${
                groupBy === opt.value ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {groups.map(({ key, label, cards: groupCards }) => {
        const totalQty = groupCards.reduce((sum, c) => sum + (c.quantity || c.qty || 1), 0)
        return (
          <div key={key}>
            <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              {label} ({totalQty})
            </h4>
            <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8 gap-2">
              {groupCards.map((card, i) => {
                const qty = card.quantity || card.qty || 1
                const stackCount = Math.min(qty, 4)
                return (
                  <div key={`${card.name}-${i}`}>
                    <div className="relative" style={{ paddingTop: `${((stackCount - 1) * GAP_WIDTH_PCT).toFixed(2)}%` }}>
                      <img
                        src={`/card-images/${card.image}`}
                        alt=""
                        aria-hidden="true"
                        className="w-full"
                        style={{ visibility: 'hidden' }}
                      />
                      {Array.from({ length: stackCount }).map((_, j) => {
                        const isFront = j === stackCount - 1
                        return (
                          <div
                            key={j}
                            className="absolute top-0 left-0 w-full"
                            style={{
                              transform: `translateY(${j * GAP_PCT}%)`,
                              zIndex: j + 1,
                            }}
                          >
                            <img
                              src={`/card-images/${card.image}`}
                              alt={isFront ? card.name : ''}
                              aria-hidden={!isFront || undefined}
                              className="w-full rounded"
                              style={{ filter: 'drop-shadow(0 3px 6px rgba(0,0,0,0.55))' }}
                              loading="lazy"
                            />
                            {isFront && qty > 1 && (
                              <span
                                className="absolute bottom-1 right-1 bg-black/70 text-white text-xs font-bold px-1.5 py-0.5 rounded"
                              >
                                x{qty}
                              </span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                    <p className="text-xs text-text-muted text-center mt-1 truncate">{card.name}</p>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
