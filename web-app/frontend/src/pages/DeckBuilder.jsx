import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { fetchDeckFromUrl, fetchAllCards, saveNewDeck, updateSavedDeck, listMyDecks, loadSavedDeck, deleteSavedDeck } from '@/api/deckBuilder'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'

// ─── Constants ───────────────────────────────────────────────────────────────

const CARD_TYPE_ORDER = ['Avatar', 'Minion', 'Magic', 'Artifact', 'Aura', 'Site']
const ELEMENTS = ['Air', 'Earth', 'Fire', 'Water']
const RARITIES = ['Ordinary', 'Exceptional', 'Elite', 'Unique']

const GROUP_OPTIONS = [
  { value: 'type', label: 'Type' },
  { value: 'cost', label: 'Mana Cost' },
  { value: 'element', label: 'Element' },
  { value: 'rarity', label: 'Rarity' },
  { value: 'subtype', label: 'Sub-Type' },
  { value: 'set', label: 'Set' },
  { value: 'tag', label: 'Custom Tag' },
  { value: 'flat', label: 'All Cards' },
]

const SORT_OPTIONS = [
  { value: 'name', label: 'Name' },
  { value: 'cost', label: 'Mana Cost' },
  { value: 'type', label: 'Type' },
  { value: 'element', label: 'Element' },
  { value: 'rarity', label: 'Rarity' },
  { value: 'attack', label: 'Attack' },
  { value: 'defence', label: 'Defense' },
  { value: 'quantity', label: 'Quantity' },
]

const LAYOUT_MODES = [
  { value: 'grid', label: 'Grid' },
  { value: 'list', label: 'List' },
  { value: 'pile', label: 'Pile' },
  { value: 'sandbox', label: 'Sandbox' },
]

const TYPE_COLORS = {
  Avatar: '#f59e0b',
  Minion: '#ef4444',
  Magic: '#3b82f6',
  Artifact: '#a855f7',
  Aura: '#eab308',
  Site: '#22c55e',
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
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getCardType(card) {
  const type = (card.type || '').toLowerCase()
  if (type.includes('avatar')) return 'Avatar'
  if (type.includes('minion')) return 'Minion'
  if (type.includes('magic')) return 'Magic'
  if (type.includes('artifact')) return 'Artifact'
  if (type.includes('aura')) return 'Aura'
  if (type.includes('site')) return 'Site'
  return 'Other'
}

function getManaCost(card) {
  return card.cost ?? card.threshold ?? card.mana_cost ?? 0
}

function getCardElements(card) {
  const el = card.elements || 'None'
  if (el === 'None' || !el) return []
  return el.split(',').map((e) => e.trim()).filter(Boolean)
}

function cardMatchesFilter(card, filters) {
  // Text search
  if (filters.textSearch) {
    const q = filters.textSearch.toLowerCase()
    const searchable = [
      card.name, card.rules_text, card.flavor_text, card.artist,
      card.sub_types, card.type_text,
    ].filter(Boolean).join(' ').toLowerCase()
    if (!searchable.includes(q)) return false
  }

  // Type filter
  if (filters.type && filters.type !== 'Any') {
    if (getCardType(card) !== filters.type) return false
  }

  // Rarity filter
  if (filters.rarities?.length) {
    if (!filters.rarities.includes(card.rarity)) return false
  }

  // Mana cost
  if (filters.costOp && filters.costValue !== '') {
    const cost = getManaCost(card)
    const val = Number(filters.costValue)
    if (filters.costOp === 'eq' && cost !== val) return false
    if (filters.costOp === 'lte' && cost > val) return false
    if (filters.costOp === 'gte' && cost < val) return false
  }

  // Include elements
  if (filters.includeElements?.length) {
    const cardEls = getCardElements(card)
    if (!filters.includeElements.some((el) => cardEls.includes(el))) return false
  }

  // Exclude elements
  if (filters.excludeElements?.length) {
    const cardEls = getCardElements(card)
    if (filters.excludeElements.some((el) => cardEls.includes(el))) return false
  }

  // Threshold filters
  for (const el of ['air', 'earth', 'fire', 'water']) {
    const key = `${el}ThresholdOp`
    const valKey = `${el}ThresholdValue`
    if (filters[key] && filters[valKey] !== '') {
      const threshold = card[`${el}_threshold`] ?? 0
      const val = Number(filters[valKey])
      if (filters[key] === 'eq' && threshold !== val) return false
      if (filters[key] === 'lte' && threshold > val) return false
      if (filters[key] === 'gte' && threshold < val) return false
    }
  }

  // Attack
  if (filters.attackOp && filters.attackValue !== '') {
    const atk = card.attack ?? -1
    const val = Number(filters.attackValue)
    if (filters.attackOp === 'eq' && atk !== val) return false
    if (filters.attackOp === 'lte' && atk > val) return false
    if (filters.attackOp === 'gte' && atk < val) return false
  }

  // Defense
  if (filters.defenceOp && filters.defenceValue !== '') {
    const def = card.defence ?? -1
    const val = Number(filters.defenceValue)
    if (filters.defenceOp === 'eq' && def !== val) return false
    if (filters.defenceOp === 'lte' && def > val) return false
    if (filters.defenceOp === 'gte' && def < val) return false
  }

  // Avatar Life
  if (filters.lifeOp && filters.lifeValue !== '') {
    const life = card.life ?? -1
    const val = Number(filters.lifeValue)
    if (filters.lifeOp === 'eq' && life !== val) return false
    if (filters.lifeOp === 'lte' && life > val) return false
    if (filters.lifeOp === 'gte' && life < val) return false
  }

  // Sub-type
  if (filters.subType) {
    const st = (card.sub_types || '').toLowerCase()
    if (!st.includes(filters.subType.toLowerCase())) return false
  }

  // Set
  if (filters.set) {
    const sets = (card.all_sets || []).map((s) => s.toLowerCase())
    if (!sets.some((s) => s.includes(filters.set.toLowerCase()))) return false
  }

  // Artist
  if (filters.artist) {
    if (!(card.artist || '').toLowerCase().includes(filters.artist.toLowerCase())) return false
  }

  // Keywords (in rules text)
  if (filters.keywords) {
    const rt = (card.rules_text || '').toLowerCase()
    if (!rt.includes(filters.keywords.toLowerCase())) return false
  }

  return true
}

function sortCards(cards, sortBy, sortDir) {
  const dir = sortDir === 'desc' ? -1 : 1
  return [...cards].sort((a, b) => {
    let va, vb
    switch (sortBy) {
      case 'name':
        return dir * (a.name || '').localeCompare(b.name || '')
      case 'cost':
        return dir * (getManaCost(a) - getManaCost(b)) || (a.name || '').localeCompare(b.name || '')
      case 'type':
        va = CARD_TYPE_ORDER.indexOf(getCardType(a))
        vb = CARD_TYPE_ORDER.indexOf(getCardType(b))
        return dir * (va - vb) || (a.name || '').localeCompare(b.name || '')
      case 'element':
        va = getCardElements(a).join(',')
        vb = getCardElements(b).join(',')
        return dir * va.localeCompare(vb) || (a.name || '').localeCompare(b.name || '')
      case 'rarity':
        va = RARITIES.indexOf(a.rarity || '')
        vb = RARITIES.indexOf(b.rarity || '')
        return dir * (va - vb) || (a.name || '').localeCompare(b.name || '')
      case 'attack':
        return dir * ((a.attack ?? -1) - (b.attack ?? -1)) || (a.name || '').localeCompare(b.name || '')
      case 'defence':
        return dir * ((a.defence ?? -1) - (b.defence ?? -1)) || (a.name || '').localeCompare(b.name || '')
      case 'quantity':
        return dir * ((a.quantity || 1) - (b.quantity || 1)) || (a.name || '').localeCompare(b.name || '')
      default:
        return 0
    }
  })
}

function groupCards(cards, groupBy, cardTags) {
  if (groupBy === 'flat') {
    return [{ key: 'all', label: `All Cards`, cards }]
  }

  const groups = {}

  if (groupBy === 'tag') {
    // Group by custom tags
    cards.forEach((card) => {
      const tags = cardTags[card.name] || ['Untagged']
      tags.forEach((tag) => {
        if (!groups[tag]) groups[tag] = []
        groups[tag].push(card)
      })
    })
    return Object.keys(groups).sort().map((tag) => ({
      key: `tag-${tag}`,
      label: tag,
      cards: groups[tag],
    }))
  }

  cards.forEach((card) => {
    let key
    switch (groupBy) {
      case 'type':
        key = getCardType(card)
        break
      case 'cost':
        key = String(getManaCost(card))
        break
      case 'element': {
        const els = getCardElements(card)
        key = els.length ? els.join('/') : 'Colorless'
        break
      }
      case 'rarity':
        key = card.rarity || 'Unknown'
        break
      case 'subtype':
        key = card.sub_types || 'None'
        break
      case 'set':
        key = card.set || 'Unknown'
        break
      default:
        key = 'Other'
    }
    if (!groups[key]) groups[key] = []
    groups[key].push(card)
  })

  // Sort group keys
  let sortedKeys = Object.keys(groups)
  if (groupBy === 'type') {
    sortedKeys = [...CARD_TYPE_ORDER, 'Other'].filter((t) => groups[t])
  } else if (groupBy === 'cost') {
    sortedKeys.sort((a, b) => Number(a) - Number(b))
  } else if (groupBy === 'rarity') {
    sortedKeys = [...RARITIES, 'Unknown'].filter((r) => groups[r])
  } else {
    sortedKeys.sort()
  }

  return sortedKeys.map((key) => {
    let label = key
    if (groupBy === 'type' && key === 'Site') label = 'Atlas'
    if (groupBy === 'cost') label = `Cost ${key}`
    return { key: `${groupBy}-${key}`, label, cards: groups[key] }
  })
}

// ─── Mana Curve Bar Graph ────────────────────────────────────────────────────

function ManaCurve({ cards }) {
  const curve = useMemo(() => {
    const buckets = {}
    cards.forEach((card) => {
      if (getCardType(card) === 'Site' || getCardType(card) === 'Avatar') return
      const cost = getManaCost(card)
      const qty = card.quantity || 1
      buckets[cost] = (buckets[cost] || 0) + qty
    })
    const keys = Object.keys(buckets).map(Number).sort((a, b) => a - b)
    if (!keys.length) return []
    const min = keys[0]
    const max = keys[keys.length - 1]
    const result = []
    for (let i = min; i <= max; i++) {
      result.push({ cost: i, count: buckets[i] || 0 })
    }
    return result
  }, [cards])

  if (!curve.length) return null
  const maxCount = Math.max(...curve.map((c) => c.count), 1)

  const W = 280
  const H = 90
  const PAD_L = 4
  const PAD_R = 4
  const PAD_T = 14
  const PAD_B = 16
  const graphH = H - PAD_T - PAD_B
  const n = curve.length
  const barW = Math.min(24, (W - PAD_L - PAD_R) / n - 2)
  const gap = n > 1 ? ((W - PAD_L - PAD_R) - barW * n) / (n - 1) : 0

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-xs" preserveAspectRatio="xMidYMid meet">
      {curve.map(({ cost, count }, i) => {
        const barH = maxCount > 0 ? (count / maxCount) * graphH : 0
        const x = PAD_L + i * (barW + gap)
        const y = PAD_T + graphH - barH
        return (
          <g key={cost}>
            <rect
              x={x} y={y} width={barW} height={Math.max(barH, 1)}
              rx={2}
              fill="currentColor" className="text-secondary/60"
            />
            {count > 0 && (
              <text x={x + barW / 2} y={y - 3} textAnchor="middle" className="fill-text-muted" style={{ fontSize: '9px' }}>
                {count}
              </text>
            )}
            <text x={x + barW / 2} y={H - 2} textAnchor="middle" className="fill-text-muted" style={{ fontSize: '9px' }}>
              {cost}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// ─── Deck Stats Summary ──────────────────────────────────────────────────────

/* ---- Horizontal Bar Chart (for keywords, subtypes, etc.) ---- */
function HorizontalBarChart({ entries, maxCount, color = 'text-secondary' }) {
  if (!entries.length) return null
  return (
    <div className="space-y-1">
      {entries.map(({ label, count }) => (
        <div key={label} className="flex items-center gap-2 text-xs">
          <span className="w-24 text-text-muted truncate text-right shrink-0">{label}</span>
          <div className="flex-1 h-4 bg-bg-elevated rounded overflow-hidden">
            <div
              className={`h-full ${color} rounded`}
              style={{ width: `${maxCount > 0 ? (count / maxCount) * 100 : 0}%`, backgroundColor: 'currentColor', opacity: 0.6 }}
            />
          </div>
          <span className="w-6 text-text-muted text-right shrink-0">{count}</span>
        </div>
      ))}
    </div>
  )
}

/* ---- Stacked Mana Curve (type by cost) ---- */
function StackedManaCurve({ cards }) {
  const data = useMemo(() => {
    const buckets = {} // { cost: { Minion: n, Magic: n, ... } }
    cards.forEach((card) => {
      const type = getCardType(card)
      if (type === 'Site' || type === 'Avatar') return
      const cost = getManaCost(card)
      const qty = card.quantity || 1
      if (!buckets[cost]) buckets[cost] = {}
      buckets[cost][type] = (buckets[cost][type] || 0) + qty
    })
    const costs = Object.keys(buckets).map(Number).sort((a, b) => a - b)
    if (!costs.length) return null
    const min = costs[0]
    const max = costs[costs.length - 1]
    const entries = []
    let maxTotal = 0
    for (let c = min; c <= max; c++) {
      const types = buckets[c] || {}
      const total = Object.values(types).reduce((s, v) => s + v, 0)
      if (total > maxTotal) maxTotal = total
      entries.push({ cost: c, types, total })
    }
    return { entries, maxTotal }
  }, [cards])

  if (!data || !data.entries.length) return null
  const { entries, maxTotal } = data
  const TYPES_SHOWN = ['Minion', 'Magic', 'Artifact', 'Aura']

  const W = 280
  const H = 90
  const PAD_L = 4
  const PAD_R = 4
  const PAD_T = 6
  const PAD_B = 16
  const graphH = H - PAD_T - PAD_B
  const n = entries.length
  const barW = Math.min(24, (W - PAD_L - PAD_R) / n - 2)
  const gap = n > 1 ? ((W - PAD_L - PAD_R) - barW * n) / (n - 1) : 0

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-xs" preserveAspectRatio="xMidYMid meet">
      {entries.map(({ cost, types }, i) => {
        const x = PAD_L + i * (barW + gap)
        let yOffset = PAD_T + graphH
        return (
          <g key={cost}>
            {TYPES_SHOWN.map((type) => {
              const count = types[type] || 0
              if (!count) return null
              const segH = maxTotal > 0 ? (count / maxTotal) * graphH : 0
              yOffset -= segH
              return (
                <rect key={type} x={x} y={yOffset} width={barW} height={Math.max(segH, 0.5)} rx={1}
                  fill={TYPE_COLORS[type]} opacity={0.7} />
              )
            })}
            <text x={x + barW / 2} y={H - 2} textAnchor="middle" className="fill-text-muted" style={{ fontSize: '9px' }}>
              {cost}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/* ---- Power Curve: avg attack & defense at each mana cost ---- */
function PowerCurve({ cards }) {
  const data = useMemo(() => {
    // Bucket minions by mana cost, tracking total atk/def/count
    const buckets = {}
    cards.forEach((card) => {
      if (getCardType(card) !== 'Minion') return
      if (card.attack == null || card.defence == null) return
      const cost = getManaCost(card)
      const qty = card.quantity || 1
      if (!buckets[cost]) buckets[cost] = { totalAtk: 0, totalDef: 0, count: 0 }
      buckets[cost].totalAtk += card.attack * qty
      buckets[cost].totalDef += card.defence * qty
      buckets[cost].count += qty
    })
    const costs = Object.keys(buckets).map(Number).sort((a, b) => a - b)
    if (!costs.length) return null
    const entries = costs.map((cost) => {
      const b = buckets[cost]
      return {
        cost,
        avgAtk: +(b.totalAtk / b.count).toFixed(1),
        avgDef: +(b.totalDef / b.count).toFixed(1),
        count: b.count,
      }
    })
    const maxStat = Math.max(...entries.map((e) => Math.max(e.avgAtk, e.avgDef)), 1)
    return { entries, maxStat }
  }, [cards])

  if (!data) return null
  const { entries, maxStat } = data

  const W = 280
  const H = 100
  const PAD_L = 24
  const PAD_R = 10
  const PAD_T = 12
  const PAD_B = 22
  const graphW = W - PAD_L - PAD_R
  const graphH = H - PAD_T - PAD_B
  const n = entries.length
  const xStep = n > 1 ? graphW / (n - 1) : 0

  const atkPoints = entries.map((e, i) => ({
    x: PAD_L + i * xStep,
    y: PAD_T + graphH - (e.avgAtk / maxStat) * graphH,
    val: e.avgAtk,
  }))
  const defPoints = entries.map((e, i) => ({
    x: PAD_L + i * xStep,
    y: PAD_T + graphH - (e.avgDef / maxStat) * graphH,
    val: e.avgDef,
  }))

  const atkPath = atkPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const defPath = defPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-xs" preserveAspectRatio="xMidYMid meet">
        {/* Y-axis grid */}
        {[0, 0.5, 1].map((frac) => {
          const y = PAD_T + graphH * (1 - frac)
          const val = (maxStat * frac).toFixed(0)
          return (
            <g key={frac}>
              <line x1={PAD_L} x2={W - PAD_R} y1={y} y2={y} stroke="currentColor" className="text-border" strokeWidth="0.5" />
              <text x={PAD_L - 4} y={y + 3} textAnchor="end" className="fill-text-muted" style={{ fontSize: '8px' }}>{val}</text>
            </g>
          )
        })}
        {/* Attack line */}
        <path d={atkPath} fill="none" stroke="#ef4444" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {/* Defense line */}
        <path d={defPath} fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" strokeDasharray="4 2" />
        {/* Dots + labels */}
        {atkPoints.map((p, i) => (
          <g key={`a${i}`}>
            <circle cx={p.x} cy={p.y} r="3" fill="#ef4444" />
            <text x={p.x} y={p.y - 6} textAnchor="middle" fill="#ef4444" style={{ fontSize: '8px', fontWeight: 600 }}>{p.val}</text>
          </g>
        ))}
        {defPoints.map((p, i) => (
          <g key={`d${i}`}>
            <circle cx={p.x} cy={p.y} r="3" fill="#3b82f6" />
            {/* Offset defense label to avoid overlap with attack */}
            <text x={p.x} y={p.y + 12} textAnchor="middle" fill="#3b82f6" style={{ fontSize: '8px', fontWeight: 600 }}>{p.val}</text>
          </g>
        ))}
        {/* X-axis: mana cost labels + minion count */}
        {entries.map((e, i) => (
          <g key={`x${i}`}>
            <text x={PAD_L + i * xStep} y={H - 10} textAnchor="middle" className="fill-text-muted" style={{ fontSize: '9px' }}>{e.cost}</text>
            <text x={PAD_L + i * xStep} y={H - 1} textAnchor="middle" className="fill-text-muted" style={{ fontSize: '7px' }}>({e.count})</text>
          </g>
        ))}
      </svg>
      <div className="flex gap-3 mt-1 text-[10px]">
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#ef4444] rounded inline-block" /> Avg Attack</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#3b82f6] rounded inline-block border-dashed" style={{ borderTop: '1px dashed #3b82f6', height: 0, backgroundColor: 'transparent' }} /> Avg Defense</span>
        <span className="text-text-muted">(n) = minion count</span>
      </div>
    </div>
  )
}

/* ---- Threshold Demand ---- */
function ThresholdDemand({ cards }) {
  const demands = useMemo(() => {
    const result = { air: {}, earth: {}, fire: {}, water: {} }
    cards.forEach((card) => {
      const t = card.thresholds || {}
      const qty = card.quantity || 1
      Object.entries(t).forEach(([el, val]) => {
        if (val > 0 && result[el]) {
          result[el][val] = (result[el][val] || 0) + qty
        }
      })
    })
    return result
  }, [cards])

  const hasAny = Object.values(demands).some((d) => Object.keys(d).length > 0)
  if (!hasAny) return null

  const elOrder = ['air', 'earth', 'fire', 'water']
  const elLabels = { air: 'Air', earth: 'Earth', fire: 'Fire', water: 'Water' }

  return (
    <div className="space-y-1">
      {elOrder.map((el) => {
        const buckets = demands[el]
        const keys = Object.keys(buckets).map(Number).sort((a, b) => a - b)
        if (!keys.length) return null
        const total = Object.values(buckets).reduce((s, v) => s + v, 0)
        const elKey = el.charAt(0).toUpperCase() + el.slice(1)
        return (
          <div key={el} className="flex items-center gap-2 text-xs">
            <span className="w-10 font-medium shrink-0" style={{ color: ELEMENT_COLORS[elKey] }}>{elLabels[el]}</span>
            <div className="flex gap-1 flex-1">
              {keys.map((threshold) => (
                <span key={threshold} className="px-1.5 py-0.5 rounded text-[10px]"
                  style={{ backgroundColor: ELEMENT_COLORS[elKey] + '25', color: ELEMENT_COLORS[elKey] }}>
                  {threshold}+ : {buckets[threshold]}
                </span>
              ))}
            </div>
            <span className="text-text-muted w-8 text-right">{total}</span>
          </div>
        )
      })}
    </div>
  )
}

function DeckStats({ cards }) {
  const stats = useMemo(() => {
    const total = cards.reduce((s, c) => s + (c.quantity || 1), 0)
    const typeCounts = {}
    const elementCounts = {}
    const rarityCounts = {}
    const keywordCounts = {}
    const subtypeCounts = {}
    let totalMana = 0, manaCards = 0
    let totalAtk = 0, totalDef = 0, minionCount = 0

    // Known Sorcery keywords to extract from rules text
    const KEYWORDS = [
      'Airborne', 'Burrow', 'Charge', 'Deathtouch', 'Disable', 'Durable',
      'Genesis', 'Guard', 'Immobile', 'Landbound', 'Lethal', 'Lifetap',
      'Movement', 'Projectile', 'Ranged', 'Reach', 'Reinforce', 'Scout',
      'Stealth', 'Submerge', 'Trample', 'Unique', 'Voidwalk', 'Wither',
    ]

    cards.forEach((card) => {
      const qty = card.quantity || 1
      const type = getCardType(card)
      typeCounts[type] = (typeCounts[type] || 0) + qty

      if (type !== 'Site' && type !== 'Avatar') {
        totalMana += getManaCost(card) * qty
        manaCards += qty
      }

      if (type === 'Minion' && card.attack != null && card.defence != null) {
        totalAtk += card.attack * qty
        totalDef += card.defence * qty
        minionCount += qty
      }

      getCardElements(card).forEach((el) => {
        elementCounts[el] = (elementCounts[el] || 0) + qty
      })

      // Rarity
      const rarity = card.rarity || 'Unknown'
      rarityCounts[rarity] = (rarityCounts[rarity] || 0) + qty

      // Keywords from rules text
      const rt = (card.rules_text || '').toLowerCase()
      KEYWORDS.forEach((kw) => {
        if (rt.includes(kw.toLowerCase())) {
          keywordCounts[kw] = (keywordCounts[kw] || 0) + qty
        }
      })

      // Subtypes
      if (card.sub_types) {
        card.sub_types.split(',').forEach((st) => {
          const trimmed = st.trim()
          if (trimmed) subtypeCounts[trimmed] = (subtypeCounts[trimmed] || 0) + qty
        })
      }
    })

    const elTotal = Object.values(elementCounts).reduce((s, v) => s + v, 0)
    const typeSegs = CARD_TYPE_ORDER.filter((t) => typeCounts[t]).map((t) => ({
      label: t === 'Site' ? 'Atlas' : t, count: typeCounts[t],
      pct: (typeCounts[t] / total) * 100, color: TYPE_COLORS[t] || '#6b7280',
    }))
    const elSegs = ELEMENTS.filter((e) => elementCounts[e]).map((e) => ({
      label: e, count: elementCounts[e],
      pct: elTotal ? (elementCounts[e] / elTotal) * 100 : 0, color: ELEMENT_COLORS[e],
    }))
    const raritySegs = [...RARITIES, 'Unknown'].filter((r) => rarityCounts[r]).map((r) => ({
      label: r, count: rarityCounts[r],
      pct: (rarityCounts[r] / total) * 100, color: RARITY_COLORS[r] || '#6b7280',
    }))

    // Sort keywords and subtypes by count desc
    const keywordEntries = Object.entries(keywordCounts)
      .sort(([, a], [, b]) => b - a)
      .map(([label, count]) => ({ label, count }))
    const maxKeyword = keywordEntries[0]?.count || 0

    const subtypeEntries = Object.entries(subtypeCounts)
      .sort(([, a], [, b]) => b - a)
      .map(([label, count]) => ({ label, count }))
    const maxSubtype = subtypeEntries[0]?.count || 0

    return {
      total, avgMana: manaCards ? (totalMana / manaCards).toFixed(2) : '-',
      minions: typeCounts.Minion || 0,
      spells: (typeCounts.Magic || 0) + (typeCounts.Artifact || 0) + (typeCounts.Aura || 0),
      sites: typeCounts.Site || 0,
      avgAtk: minionCount ? (totalAtk / minionCount).toFixed(1) : null,
      avgDef: minionCount ? (totalDef / minionCount).toFixed(1) : null,
      typeSegs, elSegs, raritySegs,
      keywordEntries, maxKeyword,
      subtypeEntries, maxSubtype,
    }
  }, [cards])

  const [showDetails, setShowDetails] = useState(true)

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4 space-y-4">
      {/* Top row: key numbers */}
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <div><span className="text-text-muted">Cards: </span><span className="font-medium">{stats.total}</span></div>
        <div><span className="text-text-muted">Avg Mana: </span><span className="font-medium">{stats.avgMana}</span></div>
        <div><span className="text-text-muted">Spell:Minion: </span><span className="font-medium">{stats.spells}:{stats.minions}</span></div>
        {stats.sites > 0 && <div><span className="text-text-muted">Sites: </span><span className="font-medium">{stats.sites}</span></div>}
        {stats.avgAtk && (
          <div><span className="text-text-muted">Avg Minion: </span><span className="font-medium">{stats.avgAtk}/{stats.avgDef}</span></div>
        )}
        <button
          onClick={() => setShowDetails((v) => !v)}
          className="text-xs text-secondary hover:underline ml-auto"
        >
          {showDetails ? 'Hide Details' : 'Show Details'}
        </button>
      </div>

      {showDetails && (
        <>
          {/* Row 1: Distribution bar charts */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {stats.typeSegs.length > 0 && (
              <div>
                <div className="text-text-muted font-semibold uppercase tracking-wider text-[10px] mb-2">Types</div>
                <div className="space-y-1.5">
                  {stats.typeSegs.map((s) => (
                    <div key={s.label} className="flex items-center gap-2 text-xs">
                      <span className="w-14 text-text-muted text-right shrink-0">{s.label}</span>
                      <div className="flex-1 h-4 bg-bg-elevated rounded overflow-hidden">
                        <div className="h-full rounded" style={{ width: `${s.pct}%`, backgroundColor: s.color, opacity: 0.7 }} />
                      </div>
                      <span className="w-6 font-medium text-right shrink-0">{s.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {stats.elSegs.length > 0 && (
              <div>
                <div className="text-text-muted font-semibold uppercase tracking-wider text-[10px] mb-2">Elements</div>
                <div className="space-y-1.5">
                  {stats.elSegs.map((s) => (
                    <div key={s.label} className="flex items-center gap-2 text-xs">
                      <span className="w-14 text-text-muted text-right shrink-0">{s.label}</span>
                      <div className="flex-1 h-4 bg-bg-elevated rounded overflow-hidden">
                        <div className="h-full rounded" style={{ width: `${s.pct}%`, backgroundColor: s.color, opacity: 0.7 }} />
                      </div>
                      <span className="w-12 font-medium text-right shrink-0">{s.count} <span className="text-text-muted">({Math.round(s.pct)}%)</span></span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {stats.raritySegs.length > 0 && (
              <div>
                <div className="text-text-muted font-semibold uppercase tracking-wider text-[10px] mb-2">Rarity</div>
                <div className="space-y-1.5">
                  {stats.raritySegs.map((s) => (
                    <div key={s.label} className="flex items-center gap-2 text-xs">
                      <span className="w-14 text-text-muted text-right shrink-0">{s.label}</span>
                      <div className="flex-1 h-4 bg-bg-elevated rounded overflow-hidden">
                        <div className="h-full rounded" style={{ width: `${s.pct}%`, backgroundColor: s.color, opacity: 0.7 }} />
                      </div>
                      <span className="w-6 font-medium text-right shrink-0">{s.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Row 2: Mana Curves + Minion Stats */}
          <div className="flex flex-wrap gap-6 items-start">
            <div className="min-w-[180px] max-w-xs flex-1">
              <div className="text-xs text-text-muted font-semibold uppercase tracking-wider mb-1">Mana Curve</div>
              <ManaCurve cards={cards} />
            </div>
            <div className="min-w-[180px] max-w-xs flex-1">
              <div className="text-xs text-text-muted font-semibold uppercase tracking-wider mb-1">Curve by Type</div>
              <StackedManaCurve cards={cards} />
              <div className="flex flex-wrap gap-2 mt-1">
                {['Minion', 'Magic', 'Artifact', 'Aura'].map((t) => (
                  <span key={t} className="flex items-center gap-1 text-[10px] text-text-muted">
                    <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: TYPE_COLORS[t] }} />{t}
                  </span>
                ))}
              </div>
            </div>
            <div className="min-w-[220px] max-w-xs flex-1">
              <div className="text-xs text-text-muted font-semibold uppercase tracking-wider mb-1">Power Curve</div>
              <PowerCurve cards={cards} />
            </div>
          </div>

          {/* Row 3: Threshold Demand */}
          <div>
            <div className="text-xs text-text-muted font-semibold uppercase tracking-wider mb-2">Threshold Demand</div>
            <ThresholdDemand cards={cards} />
          </div>

          {/* Row 4: Keywords + Subtypes */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {stats.keywordEntries.length > 0 && (
              <div>
                <div className="text-xs text-text-muted font-semibold uppercase tracking-wider mb-2">Keywords</div>
                <HorizontalBarChart entries={stats.keywordEntries} maxCount={stats.maxKeyword} color="text-secondary" />
              </div>
            )}
            {stats.subtypeEntries.length > 0 && (
              <div>
                <div className="text-xs text-text-muted font-semibold uppercase tracking-wider mb-2">Subtypes</div>
                <HorizontalBarChart entries={stats.subtypeEntries} maxCount={stats.maxSubtype} color="text-primary" />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Filter Panel ────────────────────────────────────────────────────────────

const DEFAULT_FILTERS = {
  textSearch: '',
  type: 'Any',
  rarities: [],
  costOp: '', costValue: '',
  includeElements: [], excludeElements: [],
  airThresholdOp: '', airThresholdValue: '',
  earthThresholdOp: '', earthThresholdValue: '',
  fireThresholdOp: '', fireThresholdValue: '',
  waterThresholdOp: '', waterThresholdValue: '',
  attackOp: '', attackValue: '',
  defenceOp: '', defenceValue: '',
  lifeOp: '', lifeValue: '',
  subType: '',
  set: '',
  artist: '',
  keywords: '',
}

const OP_OPTIONS = [
  { value: '', label: 'Any' },
  { value: 'eq', label: '=' },
  { value: 'lte', label: '<=' },
  { value: 'gte', label: '>=' },
]

function NumericFilter({ label, opKey, valKey, filters, setFilter }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-text-muted w-20 shrink-0">{label}</span>
      <select
        value={filters[opKey]}
        onChange={(e) => setFilter(opKey, e.target.value)}
        className="bg-bg-elevated border border-border rounded px-1.5 py-1 text-xs w-14"
      >
        {OP_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {filters[opKey] && (
        <input
          type="number"
          min="0"
          value={filters[valKey]}
          onChange={(e) => setFilter(valKey, e.target.value)}
          className="bg-bg-elevated border border-border rounded px-1.5 py-1 text-xs w-14"
        />
      )}
    </div>
  )
}

function ElementToggle({ elements, selected, onChange, label }) {
  return (
    <div>
      <span className="text-xs text-text-muted block mb-1">{label}</span>
      <div className="flex gap-1">
        {ELEMENTS.map((el) => {
          const active = selected.includes(el)
          return (
            <button
              key={el}
              onClick={() => onChange(active ? selected.filter((e) => e !== el) : [...selected, el])}
              className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                active
                  ? 'border-secondary bg-secondary/20 text-secondary'
                  : 'border-border text-text-muted hover:border-secondary/50'
              }`}
            >
              {el}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function FilterPanel({ filters, setFilter, resetFilters, allCards }) {
  const [expanded, setExpanded] = useState(false)

  // Collect unique sub-types and sets for autocomplete
  const { subTypes, sets, artists } = useMemo(() => {
    const st = new Set()
    const s = new Set()
    const a = new Set()
    allCards.forEach((c) => {
      if (c.sub_types) c.sub_types.split(',').forEach((t) => st.add(t.trim()))
      if (c.set) s.add(c.set)
      if (c.artist) a.add(c.artist)
    })
    return { subTypes: [...st].sort(), sets: [...s].sort(), artists: [...a].sort() }
  }, [allCards])

  const hasActiveFilters = Object.keys(DEFAULT_FILTERS).some((k) => {
    const v = filters[k]
    const d = DEFAULT_FILTERS[k]
    if (Array.isArray(v)) return v.length > 0
    return v !== d
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium text-text hover:bg-secondary/5 transition-colors"
      >
        <span className="flex items-center gap-2">
          Filters
          {hasActiveFilters && (
            <span className="w-2 h-2 rounded-full bg-secondary" />
          )}
        </span>
        <svg className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border pt-3">
          {/* Text search */}
          <input
            type="text"
            value={filters.textSearch}
            onChange={(e) => setFilter('textSearch', e.target.value)}
            placeholder="Search name, rules text, flavor text, artist..."
            className="w-full bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm"
          />

          {/* Type + Rarity row */}
          <div className="flex flex-wrap gap-4">
            <div>
              <span className="text-xs text-text-muted block mb-1">Type</span>
              <select
                value={filters.type}
                onChange={(e) => setFilter('type', e.target.value)}
                className="bg-bg-elevated border border-border rounded px-2 py-1 text-xs"
              >
                <option value="Any">Any</option>
                {CARD_TYPE_ORDER.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <span className="text-xs text-text-muted block mb-1">Rarity</span>
              <div className="flex gap-1">
                {RARITIES.map((r) => {
                  const active = filters.rarities.includes(r)
                  return (
                    <button
                      key={r}
                      onClick={() => setFilter('rarities', active ? filters.rarities.filter((x) => x !== r) : [...filters.rarities, r])}
                      className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                        active
                          ? 'text-black font-medium'
                          : 'border-border text-text-muted hover:border-secondary/50'
                      }`}
                      style={active ? { backgroundColor: RARITY_COLORS[r], borderColor: RARITY_COLORS[r] } : undefined}
                    >
                      {r}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Elements */}
          <div className="flex flex-wrap gap-4">
            <ElementToggle
              elements={ELEMENTS}
              selected={filters.includeElements}
              onChange={(v) => setFilter('includeElements', v)}
              label="Include Elements"
            />
            <ElementToggle
              elements={ELEMENTS}
              selected={filters.excludeElements}
              onChange={(v) => setFilter('excludeElements', v)}
              label="Exclude Elements"
            />
          </div>

          {/* Numeric filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            <NumericFilter label="Mana Cost" opKey="costOp" valKey="costValue" filters={filters} setFilter={setFilter} />
            <NumericFilter label="Attack" opKey="attackOp" valKey="attackValue" filters={filters} setFilter={setFilter} />
            <NumericFilter label="Defense" opKey="defenceOp" valKey="defenceValue" filters={filters} setFilter={setFilter} />
            <NumericFilter label="Avatar Life" opKey="lifeOp" valKey="lifeValue" filters={filters} setFilter={setFilter} />
            <NumericFilter label="Air Threshold" opKey="airThresholdOp" valKey="airThresholdValue" filters={filters} setFilter={setFilter} />
            <NumericFilter label="Earth Threshold" opKey="earthThresholdOp" valKey="earthThresholdValue" filters={filters} setFilter={setFilter} />
            <NumericFilter label="Fire Threshold" opKey="fireThresholdOp" valKey="fireThresholdValue" filters={filters} setFilter={setFilter} />
            <NumericFilter label="Water Threshold" opKey="waterThresholdOp" valKey="waterThresholdValue" filters={filters} setFilter={setFilter} />
          </div>

          {/* Text field filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
            <div>
              <span className="text-xs text-text-muted block mb-1">Sub-Type</span>
              <input
                list="subtypes-list"
                value={filters.subType}
                onChange={(e) => setFilter('subType', e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded px-2 py-1 text-xs"
                placeholder="e.g. Dragon"
              />
              <datalist id="subtypes-list">
                {subTypes.map((st) => <option key={st} value={st} />)}
              </datalist>
            </div>
            <div>
              <span className="text-xs text-text-muted block mb-1">Set / Expansion</span>
              <input
                list="sets-list"
                value={filters.set}
                onChange={(e) => setFilter('set', e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded px-2 py-1 text-xs"
                placeholder="e.g. Arthurian Legends"
              />
              <datalist id="sets-list">
                {sets.map((s) => <option key={s} value={s} />)}
              </datalist>
            </div>
            <div>
              <span className="text-xs text-text-muted block mb-1">Artist</span>
              <input
                list="artists-list"
                value={filters.artist}
                onChange={(e) => setFilter('artist', e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded px-2 py-1 text-xs"
                placeholder="e.g. Jeff Menges"
              />
              <datalist id="artists-list">
                {artists.map((a) => <option key={a} value={a} />)}
              </datalist>
            </div>
            <div>
              <span className="text-xs text-text-muted block mb-1">Keywords</span>
              <input
                value={filters.keywords}
                onChange={(e) => setFilter('keywords', e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded px-2 py-1 text-xs"
                placeholder="e.g. Landbound"
              />
            </div>
          </div>

          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="text-xs text-accent-red hover:underline"
            >
              Clear all filters
            </button>
          )}

        </div>
      )}
    </div>
  )
}

// ─── Add Cards Panel ─────────────────────────────────────────────────────────

function AddCardsPanel({ onAddCardToDeck }) {
  const [expanded, setExpanded] = useState(false)
  const [allCardsDb, setAllCardsDb] = useState(null) // null = not loaded, [] = loaded
  const [loadingCards, setLoadingCards] = useState(false)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('Any')
  const [elementFilter, setElementFilter] = useState('Any')
  const [page, setPage] = useState(0)

  const PAGE_SIZE = 50

  const handleExpand = () => {
    const next = !expanded
    setExpanded(next)
    if (next && allCardsDb === null) {
      setLoadingCards(true)
      fetchAllCards()
        .then((cards) => setAllCardsDb(cards))
        .catch(() => setAllCardsDb([]))
        .finally(() => setLoadingCards(false))
    }
  }

  const filtered = useMemo(() => {
    if (!allCardsDb) return []
    let list = allCardsDb
    if (search) {
      const q = search.toLowerCase()
      list = list.filter((c) =>
        c.name.toLowerCase().includes(q) ||
        (c.sub_types && c.sub_types.toLowerCase().includes(q)) ||
        (c.rules_text && c.rules_text.toLowerCase().includes(q))
      )
    }
    if (typeFilter !== 'Any') {
      list = list.filter((c) => c.type === typeFilter)
    }
    if (elementFilter !== 'Any') {
      list = list.filter((c) => {
        const els = (c.elements || '').split(/[,/]/).map((e) => e.trim())
        return els.includes(elementFilter)
      })
    }
    return list
  }, [allCardsDb, search, typeFilter, elementFilter])

  // Reset page when filters change
  useEffect(() => { setPage(0) }, [search, typeFilter, elementFilter])

  const pageCards = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  return (
    <div className="bg-bg-surface border border-border rounded-lg">
      <button
        onClick={handleExpand}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium text-text hover:bg-secondary/5 transition-colors"
      >
        <span>Add Cards</span>
        <svg className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border pt-3 space-y-3">
          {loadingCards && <Spinner className="py-4" />}
          {allCardsDb && (
            <>
              {/* Search + filters */}
              <div className="flex flex-wrap gap-2">
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name, sub-type, or rules text..."
                  className="flex-1 min-w-[200px] bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:border-secondary"
                />
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="bg-bg-elevated border border-border rounded px-2 py-1.5 text-xs"
                >
                  <option value="Any">All Types</option>
                  {CARD_TYPE_ORDER.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <select
                  value={elementFilter}
                  onChange={(e) => setElementFilter(e.target.value)}
                  className="bg-bg-elevated border border-border rounded px-2 py-1.5 text-xs"
                >
                  <option value="Any">All Elements</option>
                  {ELEMENTS.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>

              <p className="text-xs text-text-muted">{filtered.length} cards found</p>

              {/* Card list */}
              <div className="max-h-80 overflow-y-auto space-y-0.5">
                {pageCards.map((card) => (
                  <div key={card.name} className="flex items-center gap-2 px-2 py-1.5 bg-bg-elevated rounded hover:bg-bg-raised transition-colors">
                    {card.image && (
                      <img src={`/card-images/${card.image}`} alt="" className="h-10 rounded" loading="lazy" />
                    )}
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium truncate block">{card.name}</span>
                      <span className="text-xs text-text-muted">
                        {card.type}{card.cost != null ? ` \u2022 Cost ${card.cost}` : ''}
                        {card.elements && card.elements !== 'None' ? ` \u2022 ${card.elements}` : ''}
                        {card.rarity ? ` \u2022 ${card.rarity}` : ''}
                      </span>
                    </div>
                    <button
                      onClick={() => onAddCardToDeck(card)}
                      className="shrink-0 px-2.5 py-1 bg-secondary text-black rounded text-xs font-medium hover:bg-secondary/80 transition-colors"
                    >
                      Add
                    </button>
                  </div>
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 pt-1">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="px-2 py-1 text-xs border border-border rounded hover:border-secondary disabled:opacity-30 transition-colors"
                  >
                    Prev
                  </button>
                  <span className="text-xs text-text-muted">
                    {page + 1} / {totalPages}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="px-2 py-1 text-xs border border-border rounded hover:border-secondary disabled:opacity-30 transition-colors"
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Tag Manager ─────────────────────────────────────────────────────────────

function TagManager({ cardName, tags, onAddTag, onRemoveTag, allTags }) {
  const [adding, setAdding] = useState(false)
  const [input, setInput] = useState('')
  const inputRef = useRef(null)

  useEffect(() => {
    if (adding && inputRef.current) inputRef.current.focus()
  }, [adding])

  const handleAdd = () => {
    const tag = input.trim()
    if (tag) {
      onAddTag(cardName, tag)
      setInput('')
    }
    setAdding(false)
  }

  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {(tags || []).map((tag) => (
        <span key={tag} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-secondary/20 text-secondary text-[10px] rounded-full">
          {tag}
          <button onClick={() => onRemoveTag(cardName, tag)} className="hover:text-accent-red">&times;</button>
        </span>
      ))}
      {adding ? (
        <span className="inline-flex items-center gap-0.5">
          <input
            ref={inputRef}
            list="all-tags-list"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') setAdding(false) }}
            onBlur={handleAdd}
            className="bg-bg-elevated border border-border rounded px-1 py-0.5 text-[10px] w-16"
          />
          <datalist id="all-tags-list">
            {allTags.map((t) => <option key={t} value={t} />)}
          </datalist>
        </span>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="text-[10px] text-text-muted hover:text-secondary px-1"
          title="Add tag"
        >
          +tag
        </button>
      )}
    </div>
  )
}

// ─── Card Components (Grid / List / Pile) ────────────────────────────────────

const CARD_RATIO = 1.386
const GAP_PCT = 15
const GAP_WIDTH_PCT = GAP_PCT * CARD_RATIO

function CardGrid({ cards, section, onDragStart, onDrop, cardTags, onAddTag, onRemoveTag, allTags, onAddCard, onRemoveCard, onDeleteCard, onCardClick }) {
  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
      {cards.map((card, i) => {
        const qty = card.quantity || 1
        const stackCount = Math.min(qty, 4)
        return (
          <div
            key={`${card.name}-${i}`}
            draggable
            onDragStart={(e) => onDragStart(e, card, section)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(e, section)}
            className="group cursor-grab active:cursor-grabbing"
          >
            <div className="relative" style={{ paddingTop: `${((stackCount - 1) * GAP_WIDTH_PCT).toFixed(2)}%` }}>
              <img src={card.image ? `/card-images/${card.image}` : ''} alt="" className="w-full" style={{ visibility: 'hidden' }} />
              {Array.from({ length: stackCount }).map((_, j) => {
                const isFront = j === stackCount - 1
                return (
                  <div
                    key={j}
                    className="absolute top-0 left-0 w-full"
                    style={{ transform: `translateY(${j * GAP_PCT}%)`, zIndex: j + 1 }}
                  >
                    <img
                      src={card.image ? `/card-images/${card.image}` : ''}
                      alt={isFront ? card.name : ''}
                      className="w-full rounded"
                      style={{ filter: 'drop-shadow(0 3px 6px rgba(0,0,0,0.55))' }}
                      loading="lazy"
                      onClick={isFront ? () => onCardClick(card) : undefined}
                    />
                    {isFront && qty > 1 && (
                      <span className="absolute bottom-1 right-1 bg-black/70 text-white text-xs font-bold px-1.5 py-0.5 rounded">
                        x{qty}
                      </span>
                    )}
                  </div>
                )
              })}
              {/* +/- overlay */}
              <div className="absolute top-0 left-0 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" style={{ zIndex: 10 }}>
                <button onClick={(e) => { e.stopPropagation(); onAddCard(card.name, section) }} className="bg-black/70 hover:bg-green-700 text-white text-xs font-bold w-5 h-5 rounded flex items-center justify-center" title="Add copy">+</button>
                <button onClick={(e) => { e.stopPropagation(); onRemoveCard(card.name, section) }} className="bg-black/70 hover:bg-yellow-700 text-white text-xs font-bold w-5 h-5 rounded flex items-center justify-center" title="Remove copy">-</button>
                <button onClick={(e) => { e.stopPropagation(); onDeleteCard(card.name, section) }} className="bg-black/70 hover:bg-red-700 text-white text-xs font-bold w-5 h-5 rounded flex items-center justify-center" title="Remove all">&times;</button>
              </div>
            </div>
            <p className="text-xs text-text-muted text-center mt-1 truncate">{card.name}</p>
            <TagManager cardName={card.name} tags={cardTags[card.name]} onAddTag={onAddTag} onRemoveTag={onRemoveTag} allTags={allTags} />
          </div>
        )
      })}
    </div>
  )
}

function CardList({ cards, section, onDragStart, onDrop, cardTags, onAddTag, onRemoveTag, allTags, onAddCard, onRemoveCard, onDeleteCard, onCardClick }) {
  return (
    <div className="space-y-1">
      {cards.map((card, i) => (
        <div
          key={`${card.name}-${i}`}
          draggable
          onDragStart={(e) => onDragStart(e, card, section)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => onDrop(e, section)}
          className="flex items-center gap-3 px-3 py-1.5 bg-bg-surface border border-border rounded hover:border-secondary/50 cursor-grab active:cursor-grabbing"
          onClick={() => onCardClick(card)}
        >
          {card.image && (
            <img src={`/card-images/${card.image}`} alt="" className="h-10 rounded" loading="lazy" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium truncate">{card.name}</span>
              <span className="text-xs text-text-muted">x{card.quantity || 1}</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <span>{getCardType(card)}</span>
              {getManaCost(card) > 0 && <span>Cost {getManaCost(card)}</span>}
              {getCardElements(card).length > 0 && <span>{getCardElements(card).join('/')}</span>}
              {card.rarity && <span style={{ color: RARITY_COLORS[card.rarity] }}>{card.rarity}</span>}
              {card.attack != null && <span>{card.attack}/{card.defence}</span>}
            </div>
            <TagManager cardName={card.name} tags={cardTags[card.name]} onAddTag={onAddTag} onRemoveTag={onRemoveTag} allTags={allTags} />
          </div>
          {/* Quantity controls */}
          <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => onAddCard(card.name, section)} className="w-6 h-6 bg-bg-elevated border border-border rounded text-xs font-bold hover:border-green-500 hover:text-green-400 transition-colors" title="Add copy">+</button>
            <button onClick={() => onRemoveCard(card.name, section)} className="w-6 h-6 bg-bg-elevated border border-border rounded text-xs font-bold hover:border-yellow-500 hover:text-yellow-400 transition-colors" title="Remove copy">-</button>
            <button onClick={() => onDeleteCard(card.name, section)} className="w-6 h-6 bg-bg-elevated border border-border rounded text-xs font-bold hover:border-red-500 hover:text-red-400 transition-colors" title="Remove all">&times;</button>
          </div>
          {/* Threshold pips */}
          <div className="flex gap-0.5">
            {Object.entries(card.thresholds || {}).filter(([, v]) => v > 0).map(([el, v]) => (
              <span key={el} className="text-[10px] px-1 py-0.5 rounded" style={{ backgroundColor: ELEMENT_COLORS[el.charAt(0).toUpperCase() + el.slice(1)] + '30', color: ELEMENT_COLORS[el.charAt(0).toUpperCase() + el.slice(1)] }}>
                {el.charAt(0).toUpperCase()}{v}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function CardPile({ cards, section, onDragStart, onDrop, cardTags, onAddTag, onRemoveTag, allTags, onAddCard, onRemoveCard, onDeleteCard, onCardClick }) {
  // Overlapping card images, only showing top portion of each
  return (
    <div className="flex flex-wrap gap-x-1">
      {cards.map((card, i) => (
        <div
          key={`${card.name}-${i}`}
          draggable
          onDragStart={(e) => onDragStart(e, card, section)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => onDrop(e, section)}
          className="group relative cursor-grab active:cursor-grabbing"
          style={{ width: 80, marginBottom: 4 }}
        >
          {card.image && (
            <img
              src={`/card-images/${card.image}`}
              alt={card.name}
              className="w-full rounded"
              style={{ filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.5))' }}
              loading="lazy"
              onClick={() => onCardClick(card)}
            />
          )}
          {(card.quantity || 1) > 1 && (
            <span className="absolute bottom-0.5 right-0.5 bg-black/70 text-white text-[10px] font-bold px-1 rounded">
              x{card.quantity}
            </span>
          )}
          {/* +/- overlay */}
          <div className="absolute top-0 left-0 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" style={{ zIndex: 10 }}>
            <button onClick={(e) => { e.stopPropagation(); onAddCard(card.name, section) }} className="bg-black/70 hover:bg-green-700 text-white text-[10px] font-bold w-4 h-4 rounded flex items-center justify-center" title="Add copy">+</button>
            <button onClick={(e) => { e.stopPropagation(); onRemoveCard(card.name, section) }} className="bg-black/70 hover:bg-yellow-700 text-white text-[10px] font-bold w-4 h-4 rounded flex items-center justify-center" title="Remove copy">-</button>
            <button onClick={(e) => { e.stopPropagation(); onDeleteCard(card.name, section) }} className="bg-black/70 hover:bg-red-700 text-white text-[10px] font-bold w-4 h-4 rounded flex items-center justify-center" title="Remove all">&times;</button>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Sandbox Layout ─────────────────────────────────────────────────────────

const SANDBOX_CARD_W = 120
const SANDBOX_CARD_H = Math.round(SANDBOX_CARD_W * CARD_RATIO)

let _sandboxNextId = 1

function CardSandbox({ cards, onCardClick }) {
  // items on the canvas: { id, card, x, y }
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [sidebarSearch, setSidebarSearch] = useState('')
  const canvasRef = useRef(null)
  const dragRef = useRef(null)    // { startX, startY, itemId?, origPositions? }
  const selectBoxRef = useRef(null) // { startX, startY }
  const [selectBox, setSelectBox] = useState(null) // { x, y, w, h } for rubber band

  // Deduplicate sidebar: one entry per unique card name with total quantity
  const sidebarCards = useMemo(() => {
    const map = new Map()
    for (const c of cards) {
      const existing = map.get(c.name)
      if (existing) {
        existing.quantity = (existing.quantity || 1) + (c.quantity || 1)
      } else {
        map.set(c.name, { ...c })
      }
    }
    let list = [...map.values()]
    if (sidebarSearch) {
      const q = sidebarSearch.toLowerCase()
      list = list.filter((c) => c.name.toLowerCase().includes(q))
    }
    return list
  }, [cards, sidebarSearch])

  // Add card to canvas from sidebar
  const addToCanvas = useCallback((card) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    // Place near center with some randomness
    const x = Math.round(rect.width / 2 - SANDBOX_CARD_W / 2 + (Math.random() - 0.5) * 100)
    const y = Math.round(rect.height / 2 - SANDBOX_CARD_H / 2 + (Math.random() - 0.5) * 100)
    setItems((prev) => [...prev, { id: _sandboxNextId++, card, x: Math.max(0, x), y: Math.max(0, y) }])
  }, [])

  // Remove from canvas
  const removeFromCanvas = useCallback((id) => {
    setItems((prev) => prev.filter((it) => it.id !== id))
    setSelected((prev) => { const next = new Set(prev); next.delete(id); return next })
  }, [])

  // Clear all from canvas
  const clearCanvas = useCallback(() => {
    setItems([])
    setSelected(new Set())
  }, [])

  // Canvas mouse down - start drag or selection box
  const onCanvasMouseDown = useCallback((e) => {
    if (e.button !== 0) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const cx = e.clientX - rect.left + canvas.scrollLeft
    const cy = e.clientY - rect.top + canvas.scrollTop

    // Check if clicking on a card
    const target = e.target.closest('[data-sandbox-id]')
    if (target) {
      const itemId = parseInt(target.dataset.sandboxId, 10)
      // Selection logic
      if (e.shiftKey || e.ctrlKey || e.metaKey) {
        setSelected((prev) => {
          const next = new Set(prev)
          if (next.has(itemId)) next.delete(itemId); else next.add(itemId)
          return next
        })
        return
      }
      // If not already selected, make it the only selection
      setSelected((prev) => {
        if (!prev.has(itemId)) return new Set([itemId])
        return prev
      })
      // Start dragging selected items
      const currentSelected = selected.has(itemId) ? selected : new Set([itemId])
      if (!selected.has(itemId)) setSelected(new Set([itemId]))
      const origPositions = new Map()
      setItems((prev) => {
        for (const it of prev) {
          if (currentSelected.has(it.id) || it.id === itemId) {
            origPositions.set(it.id, { x: it.x, y: it.y })
          }
        }
        return prev
      })
      dragRef.current = { startX: e.clientX, startY: e.clientY, itemId, origPositions, isCard: true }
      e.preventDefault()
      return
    }

    // Click on empty canvas - start selection box
    if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
      setSelected(new Set())
    }
    selectBoxRef.current = { startX: cx, startY: cy, clientStartX: e.clientX, clientStartY: e.clientY }
    e.preventDefault()
  }, [selected])

  // Mouse move
  const onMouseMove = useCallback((e) => {
    // Card dragging
    if (dragRef.current?.isCard) {
      const dx = e.clientX - dragRef.current.startX
      const dy = e.clientY - dragRef.current.startY
      const { origPositions, itemId } = dragRef.current
      setItems((prev) => prev.map((it) => {
        const orig = origPositions.get(it.id)
        if (orig) return { ...it, x: Math.max(0, orig.x + dx), y: Math.max(0, orig.y + dy) }
        return it
      }))
      return
    }
    // Selection box
    if (selectBoxRef.current) {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const cx = e.clientX - rect.left + canvas.scrollLeft
      const cy = e.clientY - rect.top + canvas.scrollTop
      const { startX, startY } = selectBoxRef.current
      setSelectBox({
        x: Math.min(startX, cx),
        y: Math.min(startY, cy),
        w: Math.abs(cx - startX),
        h: Math.abs(cy - startY),
      })
    }
  }, [])

  // Mouse up
  const onMouseUp = useCallback(() => {
    // Finish card drag
    if (dragRef.current?.isCard) {
      dragRef.current = null
      return
    }
    // Finish selection box
    if (selectBoxRef.current && selectBox) {
      const box = selectBox
      const newSelected = new Set()
      for (const it of items) {
        const cardCx = it.x + SANDBOX_CARD_W / 2
        const cardCy = it.y + SANDBOX_CARD_H / 2
        if (cardCx >= box.x && cardCx <= box.x + box.w && cardCy >= box.y && cardCy <= box.y + box.h) {
          newSelected.add(it.id)
        }
      }
      setSelected(newSelected)
    }
    selectBoxRef.current = null
    setSelectBox(null)
    dragRef.current = null
  }, [selectBox, items])

  // Attach global mouse listeners when dragging/selecting
  useEffect(() => {
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [onMouseMove, onMouseUp])

  // Handle drop from sidebar
  const onCanvasDrop = useCallback((e) => {
    e.preventDefault()
    const cardJson = e.dataTransfer.getData('application/x-sandbox-card')
    if (!cardJson) return
    const card = JSON.parse(cardJson)
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = Math.max(0, e.clientX - rect.left + canvas.scrollLeft - SANDBOX_CARD_W / 2)
    const y = Math.max(0, e.clientY - rect.top + canvas.scrollTop - SANDBOX_CARD_H / 2)
    setItems((prev) => [...prev, { id: _sandboxNextId++, card, x, y }])
  }, [])

  // Delete selected with Delete/Backspace key
  useEffect(() => {
    const handler = (e) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selected.size > 0 && e.target === document.body) {
        setItems((prev) => prev.filter((it) => !selected.has(it.id)))
        setSelected(new Set())
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selected])

  return (
    <div className="flex gap-0 border border-border rounded-lg overflow-hidden" style={{ height: 'calc(100vh - 160px)' }}>
      {/* Sidebar - 1/4 */}
      <div className="w-1/4 min-w-[200px] max-w-[300px] bg-bg-surface border-r border-border flex flex-col">
        <div className="p-2 border-b border-border">
          <input
            type="text"
            value={sidebarSearch}
            onChange={(e) => setSidebarSearch(e.target.value)}
            placeholder="Filter cards..."
            className="w-full bg-bg-elevated border border-border rounded px-2 py-1 text-xs focus:outline-none focus:border-secondary"
          />
        </div>
        <div className="flex-1 overflow-y-auto p-1 space-y-0.5">
          {sidebarCards.map((card) => (
            <div
              key={card.name}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('application/x-sandbox-card', JSON.stringify(card))
                e.dataTransfer.effectAllowed = 'copy'
              }}
              onDoubleClick={() => addToCanvas(card)}
              className="flex items-center gap-2 px-2 py-1 rounded hover:bg-bg-elevated cursor-grab active:cursor-grabbing text-xs"
            >
              {card.image && (
                <img src={`/card-images/${card.image}`} alt="" className="h-8 rounded" loading="lazy" />
              )}
              <div className="flex-1 min-w-0">
                <span className="truncate block">{card.name}</span>
                <span className="text-text-muted text-[10px]">{card.type} {card.cost != null ? `(${card.cost})` : ''}</span>
              </div>
              <span className="text-text-muted shrink-0">x{card.quantity || 1}</span>
            </div>
          ))}
        </div>
        <div className="p-2 border-t border-border flex gap-1">
          <button onClick={clearCanvas} className="flex-1 px-2 py-1 bg-bg-elevated border border-border rounded text-xs hover:border-red-500 transition-colors">Clear</button>
          <span className="text-xs text-text-muted self-center px-1">{items.length} on canvas</span>
        </div>
      </div>

      {/* Canvas - 3/4 */}
      <div
        ref={canvasRef}
        className="flex-1 relative overflow-auto bg-bg-raised"
        onMouseDown={onCanvasMouseDown}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onCanvasDrop}
        style={{ cursor: selectBoxRef.current ? 'crosshair' : 'default' }}
      >
        {/* Canvas inner area (large so cards can be placed anywhere) */}
        <div className="relative" style={{ minWidth: 2000, minHeight: 1500 }}>
          {items.map((it) => (
            <div
              key={it.id}
              data-sandbox-id={it.id}
              className={`absolute cursor-grab active:cursor-grabbing transition-shadow ${
                selected.has(it.id) ? 'ring-2 ring-secondary rounded' : ''
              }`}
              style={{
                left: it.x,
                top: it.y,
                width: SANDBOX_CARD_W,
                zIndex: selected.has(it.id) ? 50 : 1,
              }}
            >
              {it.card.image ? (
                <img
                  src={`/card-images/${it.card.image}`}
                  alt={it.card.name}
                  className="w-full rounded"
                  style={{ filter: 'drop-shadow(0 3px 8px rgba(0,0,0,0.6))' }}
                  loading="lazy"
                  onDoubleClick={(e) => { e.stopPropagation(); onCardClick(it.card) }}
                />
              ) : (
                <div className="w-full bg-bg-elevated border border-border rounded p-1 text-[10px] text-center" style={{ height: SANDBOX_CARD_H }}>
                  {it.card.name}
                </div>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); removeFromCanvas(it.id) }}
                className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-red-600 hover:bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity"
                style={{ zIndex: 60 }}
                onMouseDown={(e) => e.stopPropagation()}
              >
                &times;
              </button>
            </div>
          ))}

          {/* Selection box */}
          {selectBox && (
            <div
              className="absolute border-2 border-secondary/60 bg-secondary/10 pointer-events-none"
              style={{ left: selectBox.x, top: selectBox.y, width: selectBox.w, height: selectBox.h, zIndex: 100 }}
            />
          )}

          {items.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <p className="text-text-muted text-sm">Drag cards from the sidebar or double-click to add them</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Card Detail Modal ───────────────────────────────────────────────────────

function CardDetailModal({ card, onClose }) {
  if (!card) return null

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="p-6">
          <div className="flex gap-4">
            {card.image && (
              <img src={`/card-images/${card.image}`} alt={card.name} className="w-48 rounded" />
            )}
            <div className="flex-1 space-y-2">
              <h3 className="text-lg font-semibold">{card.name}</h3>
              <div className="text-xs space-y-1 text-text-muted">
                <p><span className="font-medium text-text">Type:</span> {card.type}</p>
                {card.sub_types && <p><span className="font-medium text-text">Sub-types:</span> {card.sub_types}</p>}
                <p><span className="font-medium text-text">Rarity:</span> <span style={{ color: RARITY_COLORS[card.rarity] }}>{card.rarity}</span></p>
                <p><span className="font-medium text-text">Elements:</span> {card.elements === 'None' ? 'Colorless' : card.elements}</p>
                {getManaCost(card) > 0 && <p><span className="font-medium text-text">Mana Cost:</span> {getManaCost(card)}</p>}
                {card.attack != null && <p><span className="font-medium text-text">Attack/Defense:</span> {card.attack}/{card.defence}</p>}
                {card.life != null && <p><span className="font-medium text-text">Life:</span> {card.life}</p>}
                {card.thresholds && Object.entries(card.thresholds).some(([, v]) => v > 0) && (
                  <p><span className="font-medium text-text">Thresholds:</span> {Object.entries(card.thresholds).filter(([, v]) => v > 0).map(([el, v]) => `${el}: ${v}`).join(', ')}</p>
                )}
                {card.set && <p><span className="font-medium text-text">Set:</span> {card.set}</p>}
                {card.artist && <p><span className="font-medium text-text">Artist:</span> {card.artist}</p>}
              </div>
            </div>
          </div>
          {card.rules_text && (
            <div className="mt-4 p-3 bg-bg-elevated rounded text-sm">
              <p className="text-xs font-medium text-text-muted uppercase mb-1">Rules Text</p>
              <p className="whitespace-pre-wrap">{card.rules_text}</p>
            </div>
          )}
          {card.flavor_text && (
            <div className="mt-2 p-3 bg-bg-elevated rounded text-sm italic text-text-muted">
              {card.flavor_text}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Section Component (Mainboard / Sideboard) ──────────────────────────────

function DeckSection({ title, cards, section, groupBy, sortBy, sortDir, layout, cardTags, allTags, onDragStart, onDrop, onAddTag, onRemoveTag, onAddCard, onRemoveCard, onDeleteCard, onCardClick }) {
  const groups = useMemo(() => groupCards(cards, groupBy, cardTags), [cards, groupBy, cardTags])
  const sortedGroups = useMemo(() =>
    groups.map((g) => ({ ...g, cards: sortCards(g.cards, sortBy, sortDir) })),
    [groups, sortBy, sortDir]
  )

  const totalQty = cards.reduce((s, c) => s + (c.quantity || 1), 0)

  const LayoutComponent = layout === 'list' ? CardList : layout === 'pile' ? CardPile : CardGrid
  const layoutProps = { section, onDragStart, onDrop, cardTags, onAddTag, onRemoveTag, allTags, onAddCard, onRemoveCard, onDeleteCard, onCardClick }

  return (
    <div
      className="min-h-[100px] rounded-lg border-2 border-dashed border-border p-3 transition-colors"
      onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('border-secondary') }}
      onDragLeave={(e) => e.currentTarget.classList.remove('border-secondary')}
      onDrop={(e) => { e.currentTarget.classList.remove('border-secondary'); onDrop(e, section) }}
    >
      <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
        {title} ({totalQty})
      </h3>

      {sortedGroups.map(({ key, label, cards: groupCards }) => {
        const groupQty = groupCards.reduce((s, c) => s + (c.quantity || 1), 0)
        return (
          <div key={key} className="mb-4">
            {groupBy !== 'flat' && (
              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                {label} ({groupQty})
              </h4>
            )}
            <LayoutComponent cards={groupCards} {...layoutProps} />
          </div>
        )
      })}

      {cards.length === 0 && (
        <p className="text-sm text-text-muted text-center py-6">
          {section === 'sideboard' ? 'Drag cards here to add to sideboard' : 'No cards'}
        </p>
      )}
    </div>
  )
}

// ─── Main Page Component ─────────────────────────────────────────────────────

export default function DeckBuilder() {
  const { user } = useAuth()
  const [deckUrl, setDeckUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [deckName, setDeckName] = useState('')
  const [mainboard, setMainboard] = useState([])
  const [sideboard, setSideboard] = useState([])
  const [avatar, setAvatar] = useState(null)

  // Saved deck state
  const [savedDeckId, setSavedDeckId] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null)
  const [showMyDecks, setShowMyDecks] = useState(false)
  const [myDecks, setMyDecks] = useState([])
  const [decksLoading, setDecksLoading] = useState(false)
  const [deckSearch, setDeckSearch] = useState('')

  // View controls
  const [groupBy, setGroupBy] = useState('type')
  const [sortBy, setSortBy] = useState('cost')
  const [sortDir, setSortDir] = useState('asc')
  const [layout, setLayout] = useState('grid')
  const [filters, setFilters] = useState({ ...DEFAULT_FILTERS })

  // Custom tags: { cardName: ['tag1', 'tag2'] }
  const [cardTags, setCardTags] = useState({})
  const allTags = useMemo(() => {
    const tags = new Set()
    Object.values(cardTags).forEach((arr) => arr.forEach((t) => tags.add(t)))
    return [...tags].sort()
  }, [cardTags])

  // Card detail modal
  const [selectedCard, setSelectedCard] = useState(null)

  // Export state
  const [exportCopied, setExportCopied] = useState(false)

  // Drag and drop state
  const dragData = useRef(null)

  const handleFetch = async () => {
    if (!deckUrl.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDeckFromUrl(deckUrl.trim())
      setDeckName(data.name || 'Untitled Deck')
      setAvatar(data.avatar?.[0] || null)
      // Combine spellbook + atlas as mainboard
      const mb = [...(data.spellbook || []), ...(data.atlas || [])]
      setMainboard(mb)
      setSideboard(data.sideboard || [])
      setCardTags({})
      setSavedDeckId(null)
    } catch (err) {
      setError(err.message || 'Failed to fetch deck')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!deckName.trim() || mainboard.length === 0) return
    setSaving(true)
    setSaveMsg(null)
    try {
      const payload = {
        name: deckName,
        mainboard,
        sideboard,
        card_tags: cardTags,
        avatar,
        source_url: deckUrl || null,
      }
      if (savedDeckId) {
        await updateSavedDeck(savedDeckId, payload)
        setSaveMsg('Deck updated')
      } else {
        const res = await saveNewDeck(payload)
        setSavedDeckId(res.id)
        setSaveMsg('Deck saved')
      }
      setTimeout(() => setSaveMsg(null), 2000)
    } catch (err) {
      setSaveMsg(err.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const fetchMyDecks = async (search) => {
    setDecksLoading(true)
    try {
      const list = await listMyDecks(search || '')
      setMyDecks(list)
    } catch {
      setMyDecks([])
    } finally {
      setDecksLoading(false)
    }
  }

  const handleLoadSaved = async (id) => {
    setLoading(true)
    setError(null)
    try {
      const deck = await loadSavedDeck(id)
      setDeckName(deck.name || 'Untitled Deck')
      setAvatar(deck.avatar || null)
      setMainboard(deck.mainboard || [])
      setSideboard(deck.sideboard || [])
      setCardTags(deck.card_tags || {})
      setDeckUrl(deck.source_url || '')
      setSavedDeckId(deck.id)
      setShowMyDecks(false)
    } catch (err) {
      setError(err.message || 'Failed to load deck')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteSaved = async (id) => {
    try {
      await deleteSavedDeck(id)
      setMyDecks((prev) => prev.filter((d) => d.id !== id))
      if (savedDeckId === id) setSavedDeckId(null)
    } catch { /* ignore */ }
  }

  const setFilter = useCallback((key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }, [])

  const resetFilters = useCallback(() => {
    setFilters({ ...DEFAULT_FILTERS })
  }, [])

  const onAddTag = useCallback((cardName, tag) => {
    setCardTags((prev) => {
      const existing = prev[cardName] || []
      if (existing.includes(tag)) return prev
      return { ...prev, [cardName]: [...existing, tag] }
    })
  }, [])

  const onRemoveTag = useCallback((cardName, tag) => {
    setCardTags((prev) => {
      const existing = prev[cardName] || []
      return { ...prev, [cardName]: existing.filter((t) => t !== tag) }
    })
  }, [])

  // Add a copy of a card to a section
  const onAddCard = useCallback((cardName, section) => {
    const setter = section === 'mainboard' ? setMainboard : setSideboard
    setter((prev) => {
      const existing = prev.find((c) => c.name === cardName)
      if (existing) {
        return prev.map((c) => c.name === cardName ? { ...c, quantity: (c.quantity || 1) + 1 } : c)
      }
      return prev
    })
  }, [])

  // Remove one copy of a card (removes entirely if quantity reaches 0)
  const onRemoveCard = useCallback((cardName, section) => {
    const setter = section === 'mainboard' ? setMainboard : setSideboard
    setter((prev) => {
      const card = prev.find((c) => c.name === cardName)
      if (!card) return prev
      const qty = card.quantity || 1
      if (qty <= 1) {
        return prev.filter((c) => c.name !== cardName)
      }
      return prev.map((c) => c.name === cardName ? { ...c, quantity: qty - 1 } : c)
    })
  }, [])

  // Remove all copies of a card
  const onDeleteCard = useCallback((cardName, section) => {
    const setter = section === 'mainboard' ? setMainboard : setSideboard
    setter((prev) => prev.filter((c) => c.name !== cardName))
  }, [])

  // Add a new card from the card database to mainboard
  const onAddCardToDeck = useCallback((card) => {
    setMainboard((prev) => {
      const existing = prev.find((c) => c.name === card.name)
      if (existing) {
        return prev.map((c) => c.name === card.name ? { ...c, quantity: (c.quantity || 1) + 1 } : c)
      }
      return [...prev, { ...card, quantity: 1 }]
    })
  }, [])

  // Export deck in Curiosa bulk format
  const handleExport = useCallback(() => {
    const lines = mainboard.map((card) => `${card.quantity || 1} ${card.name}`)
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
      setExportCopied(true)
      setTimeout(() => setExportCopied(false), 2000)
    })
  }, [mainboard])

  // Apply filters
  const allCards = useMemo(() => [...mainboard, ...sideboard], [mainboard, sideboard])
  const filteredMainboard = useMemo(() => mainboard.filter((c) => cardMatchesFilter(c, filters)), [mainboard, filters])
  const filteredSideboard = useMemo(() => sideboard.filter((c) => cardMatchesFilter(c, filters)), [sideboard, filters])

  // Drag and drop
  const onDragStart = useCallback((e, card, fromSection) => {
    dragData.current = { card, fromSection }
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const onDrop = useCallback((e, toSection) => {
    e.preventDefault()
    if (!dragData.current) return
    const { card, fromSection } = dragData.current
    dragData.current = null

    if (fromSection === toSection) return

    // Move card between sections
    if (fromSection === 'mainboard') {
      setMainboard((prev) => {
        const idx = prev.findIndex((c) => c.name === card.name)
        if (idx === -1) return prev
        return [...prev.slice(0, idx), ...prev.slice(idx + 1)]
      })
      setSideboard((prev) => [...prev, card])
    } else {
      setSideboard((prev) => {
        const idx = prev.findIndex((c) => c.name === card.name)
        if (idx === -1) return prev
        return [...prev.slice(0, idx), ...prev.slice(idx + 1)]
      })
      setMainboard((prev) => [...prev, card])
    }
  }, [])

  const hasDeck = mainboard.length > 0 || sideboard.length > 0

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-display font-bold">Deck Builder</h1>
      <p className="text-sm text-text-muted">
        Paste a Curiosa deck URL to visualize, sort, filter, and organize your deck.
        Drag cards between mainboard and sideboard. Add custom tags for your own groupings.
      </p>

      {/* URL Input */}
      <div className="flex gap-2">
        <input
          type="url"
          value={deckUrl}
          onChange={(e) => setDeckUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleFetch() }}
          placeholder="https://curiosa.io/decks/..."
          className="flex-1 bg-bg-elevated border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-secondary"
        />
        <button
          onClick={handleFetch}
          disabled={loading || !deckUrl.trim()}
          className="px-4 py-2 bg-secondary text-black rounded font-medium text-sm hover:bg-secondary/80 transition-colors disabled:opacity-40"
        >
          {loading ? 'Loading...' : 'Load Deck'}
        </button>
        {user && (
          <button
            onClick={() => { setShowMyDecks((v) => !v); if (!showMyDecks) fetchMyDecks(deckSearch) }}
            className="px-4 py-2 bg-bg-elevated border border-border rounded font-medium text-sm hover:border-secondary transition-colors"
          >
            My Decks
          </button>
        )}
      </div>

      {/* My Decks panel */}
      {showMyDecks && user && (
        <div className="bg-bg-surface border border-border rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={deckSearch}
              onChange={(e) => setDeckSearch(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') fetchMyDecks(deckSearch) }}
              placeholder="Search your decks..."
              className="flex-1 bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:border-secondary"
            />
            <button
              onClick={() => fetchMyDecks(deckSearch)}
              className="px-3 py-1.5 bg-secondary text-black rounded text-sm font-medium hover:bg-secondary/80 transition-colors"
            >
              Search
            </button>
            <button
              onClick={() => setShowMyDecks(false)}
              className="px-2 py-1.5 text-text-muted hover:text-text text-sm"
            >
              Close
            </button>
          </div>
          {decksLoading && <Spinner className="py-4" />}
          {!decksLoading && myDecks.length === 0 && (
            <p className="text-sm text-text-muted text-center py-2">No saved decks found.</p>
          )}
          {!decksLoading && myDecks.length > 0 && (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {myDecks.map((d) => (
                <div key={d.id} className="flex items-center gap-3 px-3 py-2 bg-bg-elevated rounded hover:bg-bg-raised transition-colors">
                  <button onClick={() => handleLoadSaved(d.id)} className="flex-1 text-left min-w-0">
                    <span className="text-sm font-medium truncate block">{d.name}</span>
                    <span className="text-xs text-text-muted">{new Date(d.updated_at + 'Z').toLocaleDateString()}</span>
                  </button>
                  <button
                    onClick={() => handleDeleteSaved(d.id)}
                    className="text-xs text-text-muted hover:text-accent-red transition-colors px-2 py-1"
                    title="Delete deck"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded px-4 py-2 text-sm text-accent-red">
          {error}
        </div>
      )}

      {loading && <Spinner className="py-12" />}

      {hasDeck && !loading && (
        <>
          {/* Deck header */}
          <div className="flex items-center gap-4">
            {avatar?.image && (
              <img src={`/card-images/${avatar.image}`} alt={avatar.name} className="h-20 rounded" />
            )}
            <div className="flex-1">
              <input
                type="text"
                value={deckName}
                onChange={(e) => setDeckName(e.target.value)}
                className="text-xl font-semibold bg-transparent border-b border-transparent hover:border-border focus:border-secondary focus:outline-none w-full"
              />
              {avatar && <p className="text-sm text-text-muted">{avatar.name}</p>}
            </div>
            {user && (
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={handleSave}
                  disabled={saving || !deckName.trim() || mainboard.length === 0}
                  className="px-4 py-2 bg-secondary text-black rounded font-medium text-sm hover:bg-secondary/80 transition-colors disabled:opacity-40"
                >
                  {saving ? 'Saving...' : savedDeckId ? 'Update Deck' : 'Save Deck'}
                </button>
                {savedDeckId && (
                  <button
                    onClick={() => { setSavedDeckId(null); setSaveMsg(null) }}
                    className="px-3 py-2 bg-bg-elevated border border-border rounded text-sm hover:border-secondary transition-colors"
                    title="Save as a new copy"
                  >
                    Save As New
                  </button>
                )}
                {saveMsg && (
                  <span className="text-xs text-green-400">{saveMsg}</span>
                )}
              </div>
            )}
          </div>

          {/* Stats */}
          <DeckStats cards={allCards} />

          {/* Filter panel */}
          <FilterPanel filters={filters} setFilter={setFilter} resetFilters={resetFilters} allCards={allCards} />

          {/* Add Cards panel */}
          <AddCardsPanel onAddCardToDeck={onAddCardToDeck} />

          {/* Controls bar */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Group by */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-text-muted">Group:</span>
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value)}
                className="bg-bg-elevated border border-border rounded px-2 py-1 text-xs"
              >
                {GROUP_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>

            {/* Sort by */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-text-muted">Sort:</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="bg-bg-elevated border border-border rounded px-2 py-1 text-xs"
              >
                {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <button
                onClick={() => setSortDir((d) => d === 'asc' ? 'desc' : 'asc')}
                className="text-xs px-1.5 py-1 border border-border rounded hover:border-secondary transition-colors"
                title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
              >
                {sortDir === 'asc' ? '↑' : '↓'}
              </button>
            </div>

            {/* Layout */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-text-muted">Layout:</span>
              <div className="inline-flex bg-bg-raised border border-border rounded overflow-hidden">
                {LAYOUT_MODES.map((m) => (
                  <button
                    key={m.value}
                    onClick={() => setLayout(m.value)}
                    className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                      layout === m.value ? 'bg-secondary text-black' : 'text-text-muted hover:text-text'
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Export */}
            <button
              onClick={handleExport}
              className="ml-auto px-3 py-1.5 bg-bg-elevated border border-border rounded text-xs font-medium hover:border-secondary transition-colors"
              title="Copy deck list to clipboard (Curiosa bulk format)"
            >
              {exportCopied ? 'Copied!' : 'Export List'}
            </button>
          </div>

          {layout === 'sandbox' ? (
            <CardSandbox cards={allCards} onCardClick={setSelectedCard} />
          ) : (
            <>
              {/* Mainboard */}
              <DeckSection
                title="Mainboard"
                cards={filteredMainboard}
                section="mainboard"
                groupBy={groupBy}
                sortBy={sortBy}
                sortDir={sortDir}
                layout={layout}
                cardTags={cardTags}
                allTags={allTags}
                onDragStart={onDragStart}
                onDrop={onDrop}
                onAddTag={onAddTag}
                onRemoveTag={onRemoveTag}
                onAddCard={onAddCard}
                onRemoveCard={onRemoveCard}
                onDeleteCard={onDeleteCard}
                onCardClick={setSelectedCard}
              />

              {/* Sideboard */}
              <DeckSection
                title="Sideboard / Collection"
                cards={filteredSideboard}
                section="sideboard"
                groupBy={groupBy}
                sortBy={sortBy}
                sortDir={sortDir}
                layout={layout}
                cardTags={cardTags}
                allTags={allTags}
                onDragStart={onDragStart}
                onDrop={onDrop}
                onAddTag={onAddTag}
                onRemoveTag={onRemoveTag}
                onAddCard={onAddCard}
                onRemoveCard={onRemoveCard}
                onDeleteCard={onDeleteCard}
                onCardClick={setSelectedCard}
              />
            </>
          )}
        </>
      )}

      {/* Card detail modal */}
      <CardDetailModal card={selectedCard} onClose={() => setSelectedCard(null)} />
    </div>
  )
}
