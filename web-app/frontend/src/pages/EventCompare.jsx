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
      <p className="text-xs text-text-muted mb-4">Percentage of decks where each element is dominant (most cards)</p>
      <ResponsiveContainer width="100%" height={320}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#374151" />
          <PolarAngleAxis dataKey="element" tick={({ x, y, payload }) => {
            const color = ELEMENT_COLORS[payload.value] || '#d1d5db'
            return <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fill={color} fontSize={14} fontWeight={700}>{payload.value}</text>
          }} />
          <PolarRadiusAxis tick={{ fill: '#6b7280', fontSize: 10 }} domain={[0, 'auto']} />
          {events.map((ev, i) => (
            <Radar key={ev.folder} name={shortName(ev.name)} dataKey={ev.name} stroke={EVENT_COLORS[i % EVENT_COLORS.length]} fill={EVENT_COLORS[i % EVENT_COLORS.length]} fillOpacity={0.15} strokeWidth={2} />
          ))}
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Tooltip content={<CustomTooltip />} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Element Presence comparison — same radar style ---- */
function ElementPresenceChart({ events }) {
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
      <p className="text-xs text-text-muted mb-4">Percentage of decks containing at least one card of each element</p>
      <ResponsiveContainer width="100%" height={320}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#374151" />
          <PolarAngleAxis dataKey="element" tick={({ x, y, payload }) => {
            const color = ELEMENT_COLORS[payload.value] || '#d1d5db'
            return <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fill={color} fontSize={14} fontWeight={700}>{payload.value}</text>
          }} />
          <PolarRadiusAxis tick={{ fill: '#6b7280', fontSize: 10 }} domain={[0, 'auto']} />
          {events.map((ev, i) => (
            <Radar key={ev.folder} name={shortName(ev.name)} dataKey={ev.name} stroke={EVENT_COLORS[i % EVENT_COLORS.length]} fill={EVENT_COLORS[i % EVENT_COLORS.length]} fillOpacity={0.15} strokeWidth={2} />
          ))}
          <Legend wrapperStyle={{ fontSize: 12 }} />
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

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Element Combinations</h2>
      <p className="text-xs text-text-muted mb-4">Most common element pairings as percentage of decks</p>
      <ResponsiveContainer width="100%" height={Math.max(250, topCombos.length * 35)}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 10 }}>
          <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
          <YAxis type="category" dataKey="combo" tick={{ fill: '#d1d5db', fontSize: 11 }} width={100} />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {events.map((ev, i) => (
            <Bar key={ev.folder} dataKey={ev.name} fill={EVENT_COLORS[i % EVENT_COLORS.length]} radius={[0, 4, 4, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---- Shared Top Cards ---- */
function SharedCardsTable({ events }) {
  const cardEvents = {}
  events.forEach((ev) => {
    for (const card of ev.top_cards || []) {
      if (!cardEvents[card.name]) cardEvents[card.name] = []
      cardEvents[card.name].push({ event: ev.name, deck_percent: card.deck_percent })
    }
  })
  const shared = Object.entries(cardEvents)
    .filter(([, evts]) => evts.length >= 2)
    .sort((a, b) => {
      const avgA = a[1].reduce((s, e) => s + e.deck_percent, 0) / a[1].length
      const avgB = b[1].reduce((s, e) => s + e.deck_percent, 0) / b[1].length
      return avgB - avgA
    })
    .slice(0, 20)

  if (shared.length === 0) return null

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Most Played Cards Across Events</h2>
      <p className="text-xs text-text-muted mb-4">Cards appearing in multiple events&apos; top 20, ranked by average deck inclusion rate</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-2 text-xs text-text-muted font-semibold">Card</th>
              {events.map((ev, i) => (
                <th key={ev.folder} className="text-right py-2 px-2 text-xs font-semibold" style={{ color: EVENT_COLORS[i % EVENT_COLORS.length] }}>
                  {shortName(ev.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shared.map(([card, evts]) => (
              <tr key={card} className="border-b border-border/50 hover:bg-white/5">
                <td className="py-1.5 px-2 text-text">{card}</td>
                {events.map((ev) => {
                  const found = evts.find((e) => e.event === ev.name)
                  return (
                    <td key={ev.folder} className="py-1.5 px-2 text-right tabular-nums">
                      {found ? <span className="text-text">{found.deck_percent}%</span> : <span className="text-text-muted/40">-</span>}
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

/* ---- Main Page ---- */
export default function EventCompare() {
  usePageTitle('Compare Events')
  const [searchParams] = useSearchParams()
  const [data, setData] = useState(null)
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
      .then((d) => setData(d.events))
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
      <DiversityChart events={data} />
      <MonoMultiChart events={data} />
      <ElementCombosChart events={data} />
      <SharedCardsTable events={data} />
    </div>
  )
}
