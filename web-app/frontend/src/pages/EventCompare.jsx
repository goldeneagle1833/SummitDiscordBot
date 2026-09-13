import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Cell } from 'recharts'
import { compareEvents } from '@/api/events'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const ELEMENT_COLORS = {
  Fire: '#ef4444',
  Water: '#3b82f6',
  Earth: '#b45309',
  Air: '#38bdf8',
}

// Theme-matched palette: primary blue, gold, summit tones, muted complements
const EVENT_COLORS = [
  '#58a6ff', // primary blue
  '#ffd700', // secondary gold
  '#2a9c4a', // accent green
  '#7aaed4', // summit light
  '#c9a84c', // warm gold muted
  '#79c0ff', // primary light
  '#5b8db8', // summit
  '#8b949e', // text muted
  '#388bfd', // primary dark
  '#3d6b8f', // summit dark
]

function shortName(name) {
  if (name.length <= 25) return name
  return name.slice(0, 22) + '...'
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-3 shadow-lg">
      <p className="text-xs font-semibold text-text mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: <span className="font-semibold">{entry.value}</span>
        </p>
      ))}
    </div>
  )
}

/* ---- Overview: deck counts ---- */
function OverviewChart({ events }) {
  const data = events.map((ev) => ({
    name: shortName(ev.name),
    'Total Decks': ev.total_decks,
    'Top 8': ev.top8_count,
    'Unique Avatars': ev.unique_avatars,
  }))

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Event Overview</h2>
      <p className="text-xs text-text-muted mb-4">Total decks, top 8, and avatar diversity per event</p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ left: 0, right: 10 }}>
          <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} interval={0} angle={events.length > 4 ? -20 : 0} textAnchor={events.length > 4 ? 'end' : 'middle'} height={events.length > 4 ? 60 : 30} />
          <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Total Decks" fill="#60a5fa" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Top 8" fill="#f472b6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Unique Avatars" fill="#34d399" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Dominant Element Distribution — radar style like Element Presence ---- */
function ElementComparisonChart({ events }) {
  const [highlighted, setHighlighted] = useState(null)
  const elements = ['Fire', 'Water', 'Earth', 'Air']
  const data = elements.map((el) => {
    const row = { element: el }
    events.forEach((ev) => {
      const stat = ev.element_stats?.dominant_element?.find((e) => e.name === el)
      row[ev.name] = stat?.percent || 0
    })
    return row
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Dominant Element Distribution</h2>
      <p className="text-xs text-text-muted mb-4">Percentage of decks where each element is dominant (most cards) — click legend to highlight an event</p>
      <ResponsiveContainer width="100%" height={640}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#374151" />
          <PolarAngleAxis dataKey="element" tick={({ x, y, payload }) => {
            const color = ELEMENT_COLORS[payload.value] || '#d1d5db'
            return <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fill={color} fontSize={14} fontWeight={700}>{payload.value}</text>
          }} />
          <PolarRadiusAxis tick={{ fill: '#6b7280', fontSize: 10 }} domain={[0, 'auto']} />
          {events.map((ev, i) => {
            const isActive = !highlighted || highlighted === ev.name
            return (
              <Radar key={ev.folder} name={shortName(ev.name)} dataKey={ev.name} stroke={EVENT_COLORS[i % EVENT_COLORS.length]} fill={EVENT_COLORS[i % EVENT_COLORS.length]} fillOpacity={isActive ? 0.15 : 0.02} strokeOpacity={isActive ? 1 : 0.1} strokeWidth={isActive && highlighted ? 3 : 2} />
            )
          })}
          <Legend
            wrapperStyle={{ fontSize: 12, cursor: 'pointer' }}
            onClick={(e) => setHighlighted((prev) => prev === e.dataKey ? null : e.dataKey)}
          />
          <Tooltip content={<CustomTooltip />} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Element Presence comparison — same radar style ---- */
function ElementPresenceChart({ events }) {
  const [highlighted, setHighlighted] = useState(null)
  const elements = ['Fire', 'Water', 'Earth', 'Air']
  const data = elements.map((el) => {
    const row = { element: el }
    events.forEach((ev) => {
      const stat = ev.element_stats?.element_presence?.find((e) => e.name === el)
      row[ev.name] = stat?.percent || 0
    })
    return row
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Element Presence</h2>
      <p className="text-xs text-text-muted mb-4">Percentage of decks containing at least one card of each element — click legend to highlight an event</p>
      <ResponsiveContainer width="100%" height={640}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#374151" />
          <PolarAngleAxis dataKey="element" tick={({ x, y, payload }) => {
            const color = ELEMENT_COLORS[payload.value] || '#d1d5db'
            return <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fill={color} fontSize={14} fontWeight={700}>{payload.value}</text>
          }} />
          <PolarRadiusAxis tick={{ fill: '#6b7280', fontSize: 10 }} domain={[0, 'auto']} />
          {events.map((ev, i) => {
            const isActive = !highlighted || highlighted === ev.name
            return (
              <Radar key={ev.folder} name={shortName(ev.name)} dataKey={ev.name} stroke={EVENT_COLORS[i % EVENT_COLORS.length]} fill={EVENT_COLORS[i % EVENT_COLORS.length]} fillOpacity={isActive ? 0.15 : 0.02} strokeOpacity={isActive ? 1 : 0.1} strokeWidth={isActive && highlighted ? 3 : 2} />
            )
          })}
          <Legend
            wrapperStyle={{ fontSize: 12, cursor: 'pointer' }}
            onClick={(e) => setHighlighted((prev) => prev === e.dataKey ? null : e.dataKey)}
          />
          <Tooltip content={<CustomTooltip />} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Most Popular Avatars — stacked horizontal bars colored by event ---- */
function AvatarComparisonChart({ events }) {
  const avatarTotals = {}
  events.forEach((ev) => {
    for (const [av, count] of Object.entries(ev.avatar_counts || {})) {
      avatarTotals[av] = (avatarTotals[av] || 0) + count
    }
  })
  const topAvatars = Object.entries(avatarTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([name]) => name)

  const data = topAvatars.map((av) => {
    const row = { avatar: av }
    events.forEach((ev) => {
      row[ev.name] = ev.avatar_counts?.[av] || 0
    })
    return row
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Most Popular Avatars</h2>
      <p className="text-xs text-text-muted mb-4">Top avatars by number of players — bar segments show each event's contribution</p>
      <ResponsiveContainer width="100%" height={Math.max(300, topAvatars.length * 32)}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 10 }}>
          <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} />
          <YAxis type="category" dataKey="avatar" tick={{ fill: '#d1d5db', fontSize: 11 }} width={120} />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {events.map((ev, i) => (
            <Bar key={ev.folder} dataKey={ev.name} stackId="avatars" fill={EVENT_COLORS[i % EVENT_COLORS.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Avatar Diversity ---- */
function DiversityChart({ events }) {
  const data = events.map((ev, i) => {
    const total = ev.deck_count_used || ev.total_decks || 1
    return {
      name: shortName(ev.name),
      'Unique Avatars': ev.unique_avatars,
      'Diversity %': Math.round((ev.unique_avatars / total) * 100),
      fill: EVENT_COLORS[i % EVENT_COLORS.length],
    }
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Avatar Diversity</h2>
      <p className="text-xs text-text-muted mb-4">Unique avatars and diversity ratio (unique avatars / total decks)</p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ left: 0, right: 10 }}>
          <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} interval={0} angle={events.length > 4 ? -20 : 0} textAnchor={events.length > 4 ? 'end' : 'middle'} height={events.length > 4 ? 60 : 30} />
          <YAxis yAxisId="left" tick={{ fill: '#9ca3af', fontSize: 11 }} />
          <YAxis yAxisId="right" orientation="right" tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar yAxisId="left" dataKey="Unique Avatars" radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
          </Bar>
          <Bar yAxisId="right" dataKey="Diversity %" fill="#6b7280" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Mono vs Multi-Element ---- */
function MonoMultiChart({ events }) {
  const data = events.map((ev, i) => {
    const total = (ev.mono_count || 0) + (ev.multi_count || 0) || 1
    return {
      name: shortName(ev.name),
      'Mono %': Math.round((ev.mono_count || 0) / total * 100),
      'Multi %': Math.round((ev.multi_count || 0) / total * 100),
      mono: ev.mono_count || 0,
      multi: ev.multi_count || 0,
    }
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Mono vs Multi-Element</h2>
      <p className="text-xs text-text-muted mb-4">Percentage of decks using one element vs multiple elements</p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ left: 0, right: 10 }}>
          <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} interval={0} angle={events.length > 4 ? -20 : 0} textAnchor={events.length > 4 ? 'end' : 'middle'} height={events.length > 4 ? 60 : 30} />
          <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
          <Tooltip content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null
            const d = payload[0]?.payload
            return (
              <div className="bg-bg-surface border border-border rounded-lg p-3 shadow-lg">
                <p className="text-xs font-semibold text-text mb-1">{label}</p>
                <p className="text-xs text-purple-400">Mono: {d?.['Mono %']}% ({d?.mono} decks)</p>
                <p className="text-xs text-cyan-400">Multi: {d?.['Multi %']}% ({d?.multi} decks)</p>
              </div>
            )
          }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Mono %" stackId="mm" fill="#a78bfa" />
          <Bar dataKey="Multi %" stackId="mm" fill="#22d3ee" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Top Element Combinations ---- */
function ElementCombosChart({ events }) {
  const [highlighted, setHighlighted] = useState(null)

  // Collect all combos across events, pick top ones
  const allCombos = {}
  events.forEach((ev) => {
    for (const [combo, count] of Object.entries(ev.element_combos || {})) {
      if (combo === 'None') continue
      allCombos[combo] = (allCombos[combo] || 0) + count
    }
  })
  const topCombos = Object.entries(allCombos)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name]) => name)

  if (topCombos.length === 0) return null

  const data = topCombos.map((combo) => {
    const row = { combo }
    events.forEach((ev) => {
      const total = ev.deck_count_used || ev.total_decks || 1
      row[ev.name] = Math.round(((ev.element_combos?.[combo] || 0) / total) * 100)
    })
    return row
  })

  // Scale row height based on event count so bars stay readable
  const rowHeight = Math.max(60, events.length * 16 + 24)

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Element Combinations</h2>
      <p className="text-xs text-text-muted mb-4">Most common element pairings as percentage of decks — click legend to highlight an event</p>
      <ResponsiveContainer width="100%" height={Math.max(300, topCombos.length * rowHeight)}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 10 }} barCategoryGap="10%">
          <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
          <YAxis type="category" dataKey="combo" tick={{ fill: '#d1d5db', fontSize: 12 }} width={110} />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12, cursor: 'pointer' }}
            onClick={(e) => setHighlighted((prev) => prev === e.dataKey ? null : e.dataKey)}
          />
          {events.map((ev, i) => {
            const isActive = !highlighted || highlighted === ev.name
            return (
              <Bar
                key={ev.folder}
                dataKey={ev.name}
                fill={EVENT_COLORS[i % EVENT_COLORS.length]}
                fillOpacity={isActive ? 1 : 0.15}
                stroke={isActive ? EVENT_COLORS[i % EVENT_COLORS.length] : 'transparent'}
                strokeWidth={isActive && highlighted ? 1.5 : 0}
                radius={[0, 4, 4, 0]}
              />
            )
          })}
        </BarChart>
      </ResponsiveContainer>
      {highlighted && (
        <button
          onClick={() => setHighlighted(null)}
          className="mt-2 text-xs text-text-muted hover:text-secondary transition-colors"
        >
          Clear highlight
        </button>
      )}
    </div>
  )
}

/* ---- Rarity Distribution ---- */
function RarityChart({ events }) {
  const RARITY_ORDER = ['Ordinary', 'Exceptional', 'Elite', 'Unique']
  const RARITY_COLORS = {
    Ordinary: '#8b949e',
    Exceptional: '#58a6ff',
    Elite: '#a78bfa',
    Unique: '#ffd700',
  }

  const data = RARITY_ORDER.map((rarity) => {
    const row = { rarity }
    events.forEach((ev) => {
      const total = Object.values(ev.rarity_counts || {}).reduce((s, v) => s + v, 0) || 1
      row[ev.name] = Math.round(((ev.rarity_counts?.[rarity] || 0) / total) * 100)
    })
    return row
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Rarity Distribution</h2>
      <p className="text-xs text-text-muted mb-4">Percentage of total cards at each rarity level</p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ left: 0, right: 10 }}>
          <XAxis dataKey="rarity" tick={{ fill: '#9ca3af', fontSize: 11 }} />
          <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {events.map((ev, i) => (
            <Bar key={ev.folder} dataKey={ev.name} fill={EVENT_COLORS[i % EVENT_COLORS.length]} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Top 8 Conversion Rate ---- */
function ConversionRateChart({ events }) {
  // Show avatars that appear in top 8 and their conversion rate vs field representation
  const allAvatars = new Set()
  events.forEach((ev) => {
    Object.keys(ev.top8_avatar_counts || {}).forEach((a) => allAvatars.add(a))
  })

  if (allAvatars.size === 0) return null

  // Build per-avatar data: for each event, top8% vs field%
  const avatarData = [...allAvatars].map((avatar) => {
    let totalTop8Pct = 0
    let totalFieldPct = 0
    let eventCount = 0
    events.forEach((ev) => {
      const t8Count = ev.top8_avatar_counts?.[avatar] || 0
      const allCount = ev.all_avatar_counts?.[avatar] || 0
      const t8Total = Object.values(ev.top8_avatar_counts || {}).reduce((s, v) => s + v, 0) || 1
      const allTotal = Object.values(ev.all_avatar_counts || {}).reduce((s, v) => s + v, 0) || 1
      if (t8Count > 0 || allCount > 0) {
        totalTop8Pct += (t8Count / t8Total) * 100
        totalFieldPct += (allCount / allTotal) * 100
        eventCount++
      }
    })
    const avgTop8 = eventCount ? Math.round(totalTop8Pct / eventCount) : 0
    const avgField = eventCount ? Math.round(totalFieldPct / eventCount) : 0
    return { avatar, 'Top 8 %': avgTop8, 'Field %': avgField, diff: avgTop8 - avgField }
  })
    .filter((d) => d['Top 8 %'] > 0 || d['Field %'] > 0)
    .sort((a, b) => b.diff - a.diff)
    .slice(0, 12)

  // Element conversion
  const elements = ['Fire', 'Water', 'Earth', 'Air']
  const elementData = elements.map((el) => {
    let totalTop8Pct = 0
    let totalFieldPct = 0
    let eventCount = 0
    events.forEach((ev) => {
      const t8Count = ev.top8_element_counts?.[el] || 0
      const allCount = ev.all_element_counts?.[el] || 0
      const t8Total = Object.values(ev.top8_element_counts || {}).reduce((s, v) => s + v, 0) || 1
      const allTotal = Object.values(ev.all_element_counts || {}).reduce((s, v) => s + v, 0) || 1
      totalTop8Pct += (t8Count / t8Total) * 100
      totalFieldPct += (allCount / allTotal) * 100
      eventCount++
    })
    const avgTop8 = eventCount ? Math.round(totalTop8Pct / eventCount) : 0
    const avgField = eventCount ? Math.round(totalFieldPct / eventCount) : 0
    return { element: el, 'Top 8 %': avgTop8, 'Field %': avgField }
  })

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Top 8 Conversion Rate</h2>
      <p className="text-xs text-text-muted mb-4">Average representation in Top 8 vs the full field across events</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h3 className="text-sm font-semibold text-text mb-3">By Avatar</h3>
          <ResponsiveContainer width="100%" height={Math.max(250, avatarData.length * 32)}>
            <BarChart data={avatarData} layout="vertical" margin={{ left: 10, right: 10 }}>
              <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
              <YAxis type="category" dataKey="avatar" tick={{ fill: '#d1d5db', fontSize: 11 }} width={120} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Top 8 %" fill="#ffd700" radius={[0, 4, 4, 0]} />
              <Bar dataKey="Field %" fill="#8b949e" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-text mb-3">By Element</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={elementData} margin={{ left: 0, right: 10 }}>
              <XAxis dataKey="element" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Top 8 %" fill="#ffd700" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Field %" fill="#8b949e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

/* ---- Winner's Meta (Top 4 Finishers) ---- */
function WinnersMetaChart({ events }) {
  const hasWinners = events.some((ev) => ev.winners?.length > 0)
  if (!hasWinners) return null

  // Count avatars across all top-4 finishers
  const avatarWins = {}
  const elementWins = {}
  events.forEach((ev) => {
    for (const w of ev.winners || []) {
      avatarWins[w.avatar] = (avatarWins[w.avatar] || 0) + 1
      if (w.elements?.[0]) {
        elementWins[w.elements[0]] = (elementWins[w.elements[0]] || 0) + 1
      }
    }
  })

  const topAvatars = Object.entries(avatarWins)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)

  const elements = ['Fire', 'Water', 'Earth', 'Air']
  const elementData = elements.map((el) => ({
    element: el,
    count: elementWins[el] || 0,
  }))

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Winner&apos;s Meta</h2>
      <p className="text-xs text-text-muted mb-4">Avatars and elements used by top 8 finishers across all compared events</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h3 className="text-sm font-semibold text-text mb-3">Top Finisher Avatars</h3>
          <ResponsiveContainer width="100%" height={Math.max(200, topAvatars.length * 32)}>
            <BarChart data={topAvatars.map(([name, count]) => ({ name, count }))} layout="vertical" margin={{ left: 10, right: 10 }}>
              <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#d1d5db', fontSize: 11 }} width={120} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" name="Top 8 Appearances" radius={[0, 4, 4, 0]}>
                {topAvatars.map((_, i) => <Cell key={i} fill={EVENT_COLORS[i % EVENT_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-text mb-3">Top Finisher Elements</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={elementData} margin={{ left: 0, right: 10 }}>
              <XAxis dataKey="element" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} allowDecimals={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" name="Top 8 Appearances" radius={[4, 4, 0, 0]}>
                {elementData.map((entry) => <Cell key={entry.element} fill={ELEMENT_COLORS[entry.element] || '#8b949e'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      {/* Detailed winner table */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-2 text-xs text-text-muted font-semibold">Event</th>
              {[1,2,3,4,5,6,7,8].map((n) => (
                <th key={n} className="text-center py-2 px-2 text-xs text-text-muted font-semibold">{n}{n===1?'st':n===2?'nd':n===3?'rd':'th'}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.filter((ev) => ev.winners?.length > 0).map((ev, i) => (
              <tr key={ev.folder} className="border-b border-border/50">
                <td className="py-1.5 px-2 text-xs font-semibold" style={{ color: EVENT_COLORS[events.indexOf(ev) % EVENT_COLORS.length] }}>
                  {shortName(ev.name)}
                </td>
                {[0, 1, 2, 3, 4, 5, 6, 7].map((place) => {
                  const w = ev.winners?.[place]
                  return (
                    <td key={place} className="py-1.5 px-2 text-center text-xs">
                      {w ? (
                        <div>
                          <span className="text-text">{w.avatar}</span>
                          <span className="text-text-muted ml-1">({w.elements?.join('/') || '?'})</span>
                        </div>
                      ) : <span className="text-text-muted/40">-</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---- Card Overlap Heatmap ---- */
function CardOverlapHeatmap({ events, cardOverlap }) {
  if (!cardOverlap?.length) return null

  // Build a matrix lookup
  const overlapMap = {}
  for (const o of cardOverlap) {
    overlapMap[`${o.event_a}|${o.event_b}`] = o
    overlapMap[`${o.event_b}|${o.event_a}`] = { ...o, name_a: o.name_b, name_b: o.name_a }
  }

  const getColor = (jaccard) => {
    if (jaccard >= 70) return 'bg-green-900/60 text-green-300'
    if (jaccard >= 50) return 'bg-blue-900/50 text-blue-300'
    if (jaccard >= 30) return 'bg-yellow-900/40 text-yellow-300'
    return 'bg-bg-elevated text-text-muted'
  }

  // Compute the height needed for rotated column headers
  const headerHeight = Math.max(80, Math.min(160, events.reduce((max, ev) => Math.max(max, ev.name.length), 0) * 5))

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Card Overlap Heatmap</h2>
      <p className="text-xs text-text-muted mb-4">Jaccard similarity of card pools — higher % means more shared cards between events</p>
      <div className="overflow-x-auto">
        <table className="text-sm border-separate border-spacing-1">
          <thead>
            <tr>
              <th style={{ height: headerHeight }}></th>
              {events.map((ev, i) => (
                <th key={ev.folder} className="relative align-bottom px-1" style={{ height: headerHeight, minWidth: 64 }}>
                  <div
                    className="absolute bottom-0 left-1/2 origin-bottom-left text-xs font-semibold whitespace-nowrap"
                    style={{
                      color: EVENT_COLORS[i % EVENT_COLORS.length],
                      transform: 'rotate(-45deg)',
                      transformOrigin: 'bottom left',
                      marginLeft: 4,
                    }}
                  >
                    {ev.name}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((rowEv, ri) => (
              <tr key={rowEv.folder}>
                <td className="py-1.5 pr-3 text-xs font-semibold text-right whitespace-nowrap" style={{ color: EVENT_COLORS[ri % EVENT_COLORS.length] }}>
                  {rowEv.name}
                </td>
                {events.map((colEv, ci) => {
                  if (ri === ci) {
                    return (
                      <td key={colEv.folder} className="py-1.5 px-1 text-center">
                        <span className="inline-block w-16 py-1 rounded text-xs bg-bg-elevated text-text-muted">—</span>
                      </td>
                    )
                  }
                  const o = overlapMap[`${rowEv.folder}|${colEv.folder}`]
                  const jaccard = o?.jaccard || 0
                  return (
                    <td key={colEv.folder} className="py-1.5 px-1 text-center">
                      <span className={`inline-block w-16 py-1 rounded text-xs font-semibold ${getColor(jaccard)}`} title={`${o?.shared_cards || 0} shared / ${o?.total_unique || 0} unique`}>
                        {jaccard}%
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-text-muted mt-3">
        <span className="inline-block w-3 h-3 rounded bg-green-900/60 mr-1 align-middle"></span> &ge;70%
        <span className="inline-block w-3 h-3 rounded bg-blue-900/50 mr-1 ml-3 align-middle"></span> &ge;50%
        <span className="inline-block w-3 h-3 rounded bg-yellow-900/40 mr-1 ml-3 align-middle"></span> &ge;30%
        <span className="inline-block w-3 h-3 rounded bg-bg-elevated mr-1 ml-3 align-middle"></span> &lt;30%
      </p>
    </div>
  )
}

const RARITY_CLASSES = {
  ordinary: 'bg-gray-500/20 text-gray-400',
  exceptional: 'bg-blue-500/20 text-blue-400',
  elite: 'bg-purple-500/20 text-purple-400',
  unique: 'bg-yellow-500/20 text-yellow-400',
}

/* ---- Card Stats Table (all cards, with filters) ---- */
function CardStatsTable({ events }) {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [elementFilter, setElementFilter] = useState('')
  const [rarityFilter, setRarityFilter] = useState('')
  const [sortCol, setSortCol] = useState('avg_deck_percent')
  const [sortDir, setSortDir] = useState('desc')

  // Merge card stats from all events into a unified list
  const mergedCards = useMemo(() => {
    const cardMap = {}
    events.forEach((ev) => {
      for (const card of ev.card_stats || []) {
        if (!cardMap[card.name]) {
          cardMap[card.name] = {
            name: card.name,
            type: card.type,
            element: card.element,
            rarity: card.rarity,
            events: {},
          }
        }
        cardMap[card.name].events[ev.folder] = {
          count: card.count,
          avg_played: card.avg_played,
          deck_percent: parseFloat(card.deck_percent) || 0,
        }
      }
    })

    return Object.values(cardMap).map((card) => {
      const evEntries = Object.values(card.events)
      const totalCount = evEntries.reduce((s, e) => s + e.count, 0)
      const avgDeckPct = evEntries.reduce((s, e) => s + e.deck_percent, 0) / evEntries.length
      return {
        ...card,
        total_count: totalCount,
        avg_deck_percent: Math.round(avgDeckPct * 10) / 10,
        event_count: evEntries.length,
      }
    })
  }, [events])

  const types = useMemo(() => [...new Set(mergedCards.map((c) => c.type))].filter(Boolean).sort(), [mergedCards])
  const elements = useMemo(() => [...new Set(mergedCards.map((c) => c.element))].filter(Boolean).sort(), [mergedCards])
  const rarities = useMemo(() => [...new Set(mergedCards.map((c) => c.rarity))].filter(Boolean).sort(), [mergedCards])

  const filtered = useMemo(() => {
    let result = mergedCards
    if (search) {
      const q = search.toLowerCase()
      result = result.filter((c) => c.name.toLowerCase().includes(q))
    }
    if (typeFilter) result = result.filter((c) => c.type === typeFilter)
    if (elementFilter) result = result.filter((c) => c.element === elementFilter)
    if (rarityFilter) result = result.filter((c) => c.rarity === rarityFilter)

    if (sortCol) {
      result = [...result].sort((a, b) => {
        let av, bv
        if (sortCol.startsWith('ev_')) {
          const folder = sortCol.slice(3)
          av = a.events[folder]?.deck_percent || 0
          bv = b.events[folder]?.deck_percent || 0
        } else if (sortCol === 'name' || sortCol === 'type' || sortCol === 'element' || sortCol === 'rarity') {
          av = (a[sortCol] || '').toLowerCase()
          bv = (b[sortCol] || '').toLowerCase()
        } else {
          av = a[sortCol] || 0
          bv = b[sortCol] || 0
        }
        if (av < bv) return sortDir === 'asc' ? -1 : 1
        if (av > bv) return sortDir === 'asc' ? 1 : -1
        return 0
      })
    }
    return result
  }, [mergedCards, search, typeFilter, elementFilter, rarityFilter, sortCol, sortDir])

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortCol(col)
      setSortDir(col === 'name' || col === 'type' || col === 'element' || col === 'rarity' ? 'asc' : 'desc')
    }
  }

  const sortIcon = (col) => {
    if (sortCol !== col) return <span className="text-text-muted/40 ml-1">&#8693;</span>
    return <span className="text-secondary ml-1">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
  }

  if (mergedCards.length === 0) return null

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Card Stats Across Events</h2>
      <p className="text-xs text-text-muted mb-4">All cards played across compared events, with per-event deck inclusion rates</p>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-3">
        <input
          type="text"
          placeholder="Search cards..."
          className="flex-1 min-w-[200px] bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">All Types</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          className="bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm"
          value={elementFilter}
          onChange={(e) => setElementFilter(e.target.value)}
        >
          <option value="">All Elements</option>
          {elements.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
        <select
          className="bg-bg-raised border border-border rounded-lg px-3 py-2 text-sm"
          value={rarityFilter}
          onChange={(e) => setRarityFilter(e.target.value)}
        >
          <option value="">All Rarities</option>
          {rarities.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-white/10">
              <th className="py-3 px-2 text-left font-semibold cursor-pointer select-none" onClick={() => handleSort('name')}>
                Card{sortIcon('name')}
              </th>
              <th className="py-3 px-2 text-left font-semibold cursor-pointer select-none hidden md:table-cell" onClick={() => handleSort('type')}>
                Type{sortIcon('type')}
              </th>
              <th className="py-3 px-2 text-left font-semibold cursor-pointer select-none hidden md:table-cell" onClick={() => handleSort('element')}>
                Element{sortIcon('element')}
              </th>
              <th className="py-3 px-2 text-left font-semibold cursor-pointer select-none hidden sm:table-cell" onClick={() => handleSort('rarity')}>
                Rarity{sortIcon('rarity')}
              </th>
              <th className="py-3 px-2 text-right font-semibold cursor-pointer select-none" onClick={() => handleSort('total_count')}>
                Total{sortIcon('total_count')}
              </th>
              <th className="py-3 px-2 text-right font-semibold cursor-pointer select-none hidden sm:table-cell" onClick={() => handleSort('avg_deck_percent')}>
                Avg %{sortIcon('avg_deck_percent')}
              </th>
              {events.map((ev, i) => (
                <th key={ev.folder} className="py-3 px-2 text-right font-semibold text-xs cursor-pointer select-none hidden lg:table-cell" style={{ color: EVENT_COLORS[i % EVENT_COLORS.length] }} onClick={() => handleSort(`ev_${ev.folder}`)}>
                  {shortName(ev.name)}{sortIcon(`ev_${ev.folder}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((card) => {
              const rarityClass = RARITY_CLASSES[card.rarity?.toLowerCase()] || 'bg-gray-500/20 text-gray-400'
              return (
                <tr key={card.name} className="border-t border-border/30 hover:bg-white/5">
                  <td className="py-2 px-2 text-text">{card.name}</td>
                  <td className="py-2 px-2 text-text-muted hidden md:table-cell">{card.type}</td>
                  <td className="py-2 px-2 text-text-muted hidden md:table-cell">{card.element}</td>
                  <td className="py-2 px-2 hidden sm:table-cell">
                    <span className={`text-xs px-2 py-0.5 rounded ${rarityClass}`}>{card.rarity}</span>
                  </td>
                  <td className="py-2 px-2 text-right tabular-nums">
                    <span className="bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded font-semibold text-xs">{card.total_count}</span>
                  </td>
                  <td className="py-2 px-2 text-right tabular-nums font-semibold text-secondary hidden sm:table-cell">{card.avg_deck_percent}%</td>
                  {events.map((ev) => {
                    const evData = card.events[ev.folder]
                    return (
                      <td key={ev.folder} className="py-2 px-2 text-right tabular-nums hidden lg:table-cell">
                        {evData ? <span className="text-text">{evData.deck_percent}%</span> : <span className="text-text-muted/40">-</span>}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={6 + events.length} className="py-6 text-center text-text-muted">No cards match your filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-text-muted mt-2">{filtered.length} cards shown</p>
    </div>
  )
}

/* ---- Main Page ---- */
export default function EventCompare() {
  usePageTitle('Compare Events')
  const [searchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [cardOverlap, setCardOverlap] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [top8Only, setTop8Only] = useState(false)

  const folders = useMemo(() => {
    const raw = searchParams.get('events') || ''
    return raw.split(',').filter(Boolean)
  }, [searchParams])

  const fetchData = useCallback(() => {
    if (folders.length < 2) {
      setError('Select at least 2 events to compare')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    compareEvents(folders, { top8Only })
      .then((d) => {
        setData(d.events)
        setCardOverlap(d.card_overlap || null)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [folders, top8Only])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <Spinner className="py-20" />
  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-accent-red mb-4">{error}</p>
        <Link to="/top-8" className="text-sm text-secondary hover:underline">Back to Events</Link>
      </div>
    )
  }
  if (!data?.length) return null

  return (
    <div>
      <section className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Link to="/top-8" className="text-text-muted hover:text-secondary text-sm transition-colors">&larr; Events</Link>
        </div>
        <h1 className="text-2xl font-display text-secondary mb-2">Compare Events</h1>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {data.map((ev, i) => (
            <Link
              key={ev.folder}
              to={`/top-8/${ev.folder}`}
              className="text-xs px-2.5 py-1 rounded-full border transition-colors hover:opacity-80"
              style={{ borderColor: EVENT_COLORS[i % EVENT_COLORS.length], color: EVENT_COLORS[i % EVENT_COLORS.length] }}
            >
              {ev.name} ({ev.deck_count_used} decks)
            </Link>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTop8Only(false)}
            className={`text-xs px-3 py-1.5 rounded font-semibold transition-colors ${
              !top8Only ? 'bg-secondary text-black' : 'bg-bg-raised border border-border text-text-muted hover:text-text'
            }`}
          >
            All Decks
          </button>
          <button
            onClick={() => setTop8Only(true)}
            className={`text-xs px-3 py-1.5 rounded font-semibold transition-colors ${
              top8Only ? 'bg-secondary text-black' : 'bg-bg-raised border border-border text-text-muted hover:text-text'
            }`}
          >
            Top 8 Only
          </button>
        </div>
      </section>

      <OverviewChart events={data} />
      <ElementComparisonChart events={data} />
      <ElementPresenceChart events={data} />
      <AvatarComparisonChart events={data} />
      <RarityChart events={data} />
      <DiversityChart events={data} />
      <MonoMultiChart events={data} />
      <ConversionRateChart events={data} />
      <WinnersMetaChart events={data} />
      <ElementCombosChart events={data} />
      <CardOverlapHeatmap events={data} cardOverlap={cardOverlap} />
      <CardStatsTable events={data} />
    </div>
  )
}
