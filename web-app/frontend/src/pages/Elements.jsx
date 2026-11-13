import { useState, useEffect, useCallback, useMemo } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import RankedList from '@/components/analytics/RankedList'
import { getAvatarImageFiles } from '@/api/cards'
import AvatarMetaChart from '@/components/analytics/AvatarMetaChart'
import TimelineControls, { windowDays, moveMs, DEFAULT_SPEED } from '@/components/analytics/TimelineControls'
import { mergeDates, buildCumulative, flattenElementDays, elementStatsAt } from '@/utils/elementTimeline'
import { DeckTypeFilters, DeckTypeResults, deckTypeMatchups } from '@/components/meta/DeckTypeMatchups'
import MatchupLoops from '@/components/meta/MatchupLoops'

/** Winner-vs-loser deck totals for the days in the window, as deckTypeMatchups takes them. */
function matchupGamesIn(matchups, dates, endIdx, days) {
  if (!matchups || endIdx < 0) return []
  const start = days == null ? 0 : Math.max(0, endIdx - days + 1)
  const totals = {}
  for (let i = start; i <= endIdx; i++) {
    for (const [key, n] of Object.entries(matchups[dates[i]] || {})) totals[key] = (totals[key] || 0) + n
  }
  return Object.entries(totals).map(([key, n]) => {
    const [w, l] = key.split('>')
    return { winner: w.split('|'), loser: l.split('|'), n }
  })
}

const ELEMENT_COLORS = {
  Fire: { bar: 'bg-red-500', text: 'text-red-400' },
  Water: { bar: 'bg-blue-500', text: 'text-blue-400' },
  Earth: { bar: 'bg-green-500', text: 'text-green-400' },
  Air: { bar: 'bg-cyan-400', text: 'text-cyan-300' },
}

function formatEventDate(dateStr) {
  if (!dateStr) return null
  const parts = dateStr.split(' ')[0].split('-')
  if (parts.length !== 3) return dateStr
  const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]))
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/* ---- Bar chart for element win rates ---- */
function ElementBarChart({ data, title, subtitle }) {
  if (!data?.length) return null
  const sorted = [...data].sort((a, b) => b.win_rate - a.win_rate)

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">{title}</h2>
      {subtitle && <p className="text-xs text-text-muted mb-4">{subtitle}</p>}
      <RankedList items={sorted} itemKey={(el) => el.name} gap={12} renderItem={(el) => {
          const colors = ELEMENT_COLORS[el.name] || { bar: 'bg-gray-500', text: 'text-gray-400' }
          return (
            <div className="flex items-center gap-3">
              <div className={`w-14 text-sm font-semibold ${colors.text}`}>{el.name}</div>
              <div className="flex-1 bg-bg-raised rounded-full h-6 overflow-hidden relative">
                <div
                  className={`${colors.bar} h-full rounded-full timeline-bar flex items-center justify-end pr-2`}
                  style={{ width: `${Math.max(el.win_rate, 2)}%` }}
                >
                  <span className="text-xs font-semibold text-white drop-shadow">{el.win_rate}%</span>
                </div>
              </div>
              <div className="text-xs text-text-muted w-24 text-right">{el.wins}W - {el.losses}L</div>
            </div>
          )
        }} />
    </div>
  )
}

/* ---- Presence chart (win vs loss presence) ---- */
function PresenceChart({ data }) {
  if (!data?.length) return null
  const sorted = [...data].sort((a, b) => b.win_presence - a.win_presence)

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">Element Presence</h2>
      <p className="text-xs text-text-muted mb-4">
        How often each element appears in winning vs losing decks. Delta indicates correlation, not causation.
      </p>
      <RankedList items={sorted} itemKey={(el) => el.name} gap={16} renderItem={(el) => {
          const colors = ELEMENT_COLORS[el.name] || { text: 'text-gray-400' }
          const delta = (el.win_presence - el.loss_presence).toFixed(1)
          const deltaColor = parseFloat(delta) >= 0 ? 'text-green-400' : 'text-red-400'
          return (
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-semibold ${colors.text}`}>{el.name}</span>
                <span className={`text-xs font-medium ${deltaColor}`}>
                  {parseFloat(delta) >= 0 ? '+' : ''}{delta}%
                </span>
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted w-10">Wins</span>
                  <div className="flex-1 bg-bg-raised rounded-full h-4 overflow-hidden">
                    <div
                      className="bg-green-500/70 h-full rounded-full timeline-bar flex items-center justify-end pr-1.5"
                      style={{ width: `${Math.max(el.win_presence, 1)}%` }}
                    >
                      <span className="text-[10px] font-medium text-white">{el.win_presence}%</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted w-10">Losses</span>
                  <div className="flex-1 bg-bg-raised rounded-full h-4 overflow-hidden">
                    <div
                      className="bg-red-500/70 h-full rounded-full timeline-bar flex items-center justify-end pr-1.5"
                      style={{ width: `${Math.max(el.loss_presence, 1)}%` }}
                    >
                      <span className="text-[10px] font-medium text-white">{el.loss_presence}%</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )
        }} />
      <div className="flex gap-4 mt-4 text-xs text-text-muted">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-500/70 inline-block" /> % of winning decks</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-500/70 inline-block" /> % of losing decks</span>
      </div>
    </div>
  )
}

/* ---- Combo / Composition bars ---- */
function ComboBars({ data, title, subtitle, valueKey, valueLabel, sortKey }) {
  if (!data?.length) return null
  const sorted = [...data].sort((a, b) => b[sortKey || 'win_rate'] - a[sortKey || 'win_rate'])

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5 mb-6">
      <h2 className="font-display text-secondary text-lg mb-1">{title}</h2>
      {subtitle && <p className="text-xs text-text-muted mb-4">{subtitle}</p>}
      <RankedList items={sorted} itemKey={(item) => item.name || item.elements} renderItem={(item) => {
          const elements = item.name ? item.name.split(', ') : (item.elements ? item.elements.split(', ') : [])
          const val = item[valueKey || 'win_rate']
          const label = valueLabel
            ? valueLabel(item)
            : `${item.wins}W - ${item.losses}L (${item.total})`

          return (
            <div className="flex items-center gap-3">
              <div className="w-28 flex gap-1 flex-shrink-0">
                {elements.map((el) => {
                  const colors = ELEMENT_COLORS[el.trim()] || { text: 'text-gray-400' }
                  return <span key={el} className={`text-xs font-semibold ${colors.text}`}>{el.trim()}</span>
                })}
              </div>
              <div className="flex-1 bg-bg-raised rounded-full h-5 overflow-hidden relative">
                <div
                  className="bg-secondary/60 h-full rounded-full timeline-bar"
                  style={{ width: `${Math.max(val, 1)}%` }}
                />
                <span className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold text-white">
                  {val}%
                </span>
              </div>
              <div className="text-xs text-text-muted w-32 text-right">{label}</div>
            </div>
          )
        }} />
    </div>
  )
}

/* ---- Main Page ---- */
export default function Elements() {
  usePageTitle('Elemental Win Rates')

  const [eventFilter, setEventFilter] = useState('all')
  const [events, setEvents] = useState([])
  const [timeline, setTimeline] = useState(null)
  const [meta, setMeta] = useState(null)
  const [imageFiles, setImageFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Shared by every chart: which window, ending on which day, and whether it's playing
  const [view, setView] = useState({ windowKey: 'all', endIdx: -1, playing: false, speed: DEFAULT_SPEED })
  // "Your deck" picker in the top bar for the deck type matchups section
  const [deckPick, setDeckPick] = useState({ type: '', avatar: '', view: 'avatar' })

  // Load event filters and avatar art on mount
  useEffect(() => {
    get('/api/elements/filters')
      .then((d) => setEvents(d.events || []))
      .catch(() => {})
    getAvatarImageFiles().then((f) => setImageFiles(Array.isArray(f) ? f : [])).catch(() => {})
  }, [])

  // Online only: the Paper source is hidden (nobody plays on the paper ladder)
  const fetchData = useCallback(() => {
    setLoading(true)
    setError(null)
    const qs = eventFilter !== 'all' ? `?${new URLSearchParams({ event: eventFilter })}` : ''
    Promise.all([
      get(`/api/elements/timeline${qs}`),
      get(`/api/elements/avatar-meta${qs}`).catch(() => null),
    ])
      .then(([tl, am]) => {
        setTimeline(tl)
        setMeta(am)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [eventFilter])

  useEffect(() => { fetchData() }, [fetchData])

  const dates = useMemo(() => mergeDates(timeline?.dates || [], meta?.dates || []), [timeline, meta])
  const elementCumulative = useMemo(() => buildCumulative(dates, flattenElementDays(timeline?.days)), [dates, timeline])
  const avatarCumulative = useMemo(() => buildCumulative(dates, meta?.pairs || meta?.avatars), [dates, meta])

  // New data: jump to the latest day
  useEffect(() => {
    setView((s) => ({ ...s, endIdx: dates.length - 1, playing: false }))
  }, [dates])

  const endIdx = Math.min(view.endIdx, dates.length - 1)
  const days = windowDays(view.windowKey)
  const stats = useMemo(() => elementStatsAt(elementCumulative, endIdx, days), [elementCumulative, endIdx, days])

  const { elements, dominant, splash, combinations, composition: comp } = stats
  const matchupGames = useMemo(() => matchupGamesIn(meta?.matchups, dates, endIdx, days), [meta, dates, endIdx, days])
  const deckTypes = useMemo(() => deckTypeMatchups(matchupGames), [matchupGames])
  const hasElementData = elements.some((e) => e.total > 0)

  // Bars and rows move at one pace; while playing they ease into each day's
  // values, then sit still for the rest of the step
  const motion = view.playing
    ? { '--bar-ms': `${moveMs(view.speed)}ms`, '--bar-ease': 'cubic-bezier(0.45, 0, 0.55, 1)' }
    : { '--bar-ms': '600ms', '--bar-ease': 'cubic-bezier(0.22, 1, 0.36, 1)' }

  return (
    <div style={motion}>
      {/* Hero */}
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary mb-2">Elemental Win Rates</h1>
        <p className="text-text-muted text-sm">Win rates by element based on cards in reported decklists</p>
      </section>

      {/* One filter box: Event, your deck, and the timeline that drives every chart.
          Stays in view under the nav on wider screens. */}
      <div className="sm:sticky sm:top-16 z-20 mb-6 bg-bg-surface/95 backdrop-blur border border-border rounded-lg px-4 py-3">
        <div className="grid grid-cols-1 sm:flex sm:flex-wrap items-center gap-x-5 gap-y-2">
          <div className="flex items-center gap-2">
            <label className="text-sm text-text-muted">Event:</label>
            <select
              className="bg-bg-raised border border-border rounded px-2 py-1 text-sm"
              value={eventFilter}
              onChange={(e) => setEventFilter(e.target.value)}
            >
              <option value="all">All Events</option>
              {events.map((evt) => {
                const startFmt = formatEventDate(evt.start_date)
                const endFmt = formatEventDate(evt.end_date)
                if (evt.is_active) {
                  return (
                    <option key="current" value="current">
                      {evt.event_name} ({startFmt} - Present)
                    </option>
                  )
                }
                return (
                  <option key={evt.event_id} value={String(evt.event_id)}>
                    {evt.event_name} ({startFmt} - {endFmt || '?'})
                  </option>
                )
              })}
            </select>
          </div>
          {!loading && !error && dates.length > 0 && (
            <DeckTypeFilters data={deckTypes} value={deckPick} onChange={setDeckPick} compact />
          )}
        </div>
        {!loading && !error && dates.length > 0 && (
          <div className="border-t border-border mt-3 pt-3">
            <TimelineControls
              bare
              dates={dates}
              windowKey={view.windowKey}
              endIdx={endIdx}
              playing={view.playing}
              speed={view.speed}
              onChange={setView}
            />
          </div>
        )}
      </div>

      {loading ? (
        <Spinner className="py-20" />
      ) : error ? (
        <p className="text-center text-accent-red py-8">{error}</p>
      ) : dates.length === 0 ? (
        <p className="text-center text-text-muted py-8">
          No element data available yet. Report matches with decklists to see stats!
        </p>
      ) : (
        <>

          {/* Deck type matchups: picked with "Your deck" in the top bar */}
          <section className="mb-10">
            <h2 className="text-xl font-display text-secondary mb-1 text-center">Your Deck&apos;s Matchups</h2>
            <p className="text-text-muted text-sm mb-4 text-center max-w-2xl mx-auto">
              Pick your deck type (and an Avatar if you like) in the filters at the top to see what it beats and what it loses to. Deck types use the same element groups as Deck Archetypes: a deck&apos;s top two elements by Spellbook copies. Follows the Event filter and the timeline.
            </p>
            <div className="bg-bg-surface border border-border rounded-lg p-4">
              <DeckTypeResults data={deckTypes} value={deckPick} gamesLabel="games in this window"
                               emptyText="Not enough games in this window to break matchups down by deck type. Try a longer window." />
            </div>
          </section>

          {/* Rock-paper-scissors loops between decks */}
          <section className="mb-10">
            <h2 className="text-xl font-display text-secondary mb-1 text-center">Matchup Loops</h2>
            <p className="text-text-muted text-sm mb-4 text-center max-w-2xl mx-auto">
              Rock, paper, scissors between decks: one deck beats a second, the second beats a third, and the third beats the first. Follows the Event filter and the timeline.
            </p>
            <MatchupLoops games={matchupGames} />
          </section>

          {/* Meta: avatar counts over time */}
          <section className="mb-10">
            <h2 className="text-xl font-display text-secondary mb-1 text-center">Meta</h2>
            <p className="text-text-muted text-sm mb-4 text-center">How the avatar field has changed over time</p>
            <AvatarMetaChart cumulative={avatarCumulative} endIdx={endIdx} days={days} imageFiles={imageFiles} />
          </section>

          {!hasElementData ? (
            <p className="text-center text-text-muted py-8">No element data in this window.</p>
          ) : (
            <>
              {/* Chart 1: Win Rate by Element */}
              <ElementBarChart
                data={elements}
                title="Win Rate by Element"
                subtitle="Each deck can contain multiple elements, so totals overlap. A deck with Fire and Water cards counts toward both."
              />

              {/* Chart 2: Element Presence */}
              <PresenceChart data={elements} />

              {/* Chart 3: Dominant Element Win Rate */}
              <ElementBarChart
                data={dominant}
                title="Dominant Element Win Rate"
                subtitle="Only the element with the most cards in each deck is counted. Spellbook only, no sites."
              />

              {/* Chart 4: Splash Element (admin only) */}
              {splash.length > 0 && (
                <ElementBarChart
                  data={splash}
                  title="Splash Element Win Rate"
                  subtitle="Only the element with the least cards in each deck is counted. Multi-element decks only, spellbook only."
                />
              )}

              {/* Chart 5: Element Combinations (admin only) */}
              {combinations.length > 0 && (
                <ComboBars
                  data={combinations}
                  title="Element Combination Win Rates"
                  subtitle="Win rates for specific element pairings (minimum 3 games to show)."
                  valueKey="win_rate"
                  sortKey="win_rate"
                />
              )}

              {/* Chart 6: Deck Composition (admin only) */}
              {comp.length > 0 && (
                <ComboBars
                  data={comp}
                  title="Deck Element Composition"
                  subtitle="Element combinations across all decks in the selected window (spellbook only, excludes sites)."
                  valueKey="percent"
                  sortKey="percent"
                  valueLabel={(item) => `${item.count} deck${item.count !== 1 ? 's' : ''}`}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
