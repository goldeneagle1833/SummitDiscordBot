import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRankedCards, getRankedCatalog, getRankedSeasons } from '@/api/rankedAnalytics'
import Spinner from '@/components/ui/Spinner'
import CardWinRateTable, { extraRateMetrics } from '@/components/analytics/CardWinRateTable'
import { nameKey } from '@/components/analytics/format'
import { EMPTY_MINIMUMS, indexCardMetadata, selectCardTable } from '@/vendor/analytics-ui/cardTable'

// Summit only runs constructed ranked queues, so the format is fixed.
const FORMAT = 'constructed'
const ALL_SEASONS = 'all'
const NO_FILTERS = { search: '', type: '', element: '', rarity: '', minimums: EMPTY_MINIMUMS, minimumValues: EMPTY_MINIMUMS }
const FIELD = 'bg-bg-surface border border-border rounded px-3 text-sm text-text min-h-[36px] focus:outline-none focus:border-primary'

const shortDay = (iso) => {
  if (!iso) return null
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function seasonLabel(season) {
  const range = season.through ? `${shortDay(season.from)} – ${shortDay(season.through)}` : `from ${shortDay(season.from)}`
  return `${season.name}${season.is_active ? ' (current)' : ''} · ${range}`
}

/**
 * The deck's cards as rows of the Card Win Rates table.
 *
 * Reads the same /api/ranked-analytics/cards data as the Card Win Rates page,
 * limited to the named selections (all released games, or one season). Those
 * are served from Summit's saved copy, refreshed once per release, so opening
 * this view never asks Play Sorcery Online live. No custom dates here on
 * purpose: a custom range is the one selection that would go to PSO.
 *
 * Stats are for each card across all Summit ranked games, not for this
 * particular deck list.
 */
export default function DeckCardStats({ cards, avatarName }) {
  const [seasons, setSeasons] = useState([])
  const [season, setSeason] = useState(ALL_SEASONS)
  const [catalog, setCatalog] = useState([])
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortKey, setSortKey] = useState('played')
  const [sortDirection, setSortDirection] = useState('descending')
  const [selectedCard, setSelectedCard] = useState(null)
  const requestId = useRef(0)

  const chosenSeason = seasons.find((s) => s.id === season) ?? null
  const selection = useMemo(() => {
    const s = { format: FORMAT }
    if (chosenSeason?.from) s.from = chosenSeason.from
    if (chosenSeason?.through) s.through = chosenSeason.through
    return s
  }, [chosenSeason])

  useEffect(() => {
    getRankedSeasons().then((rows) => setSeasons(Array.isArray(rows) ? rows : [])).catch(() => setSeasons([]))
    getRankedCatalog().then((rows) => setCatalog(Array.isArray(rows) ? rows : [])).catch(() => setCatalog([]))
  }, [])

  useEffect(() => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    setSelectedCard(null)
    getRankedCards(selection)
      .then((body) => { if (id === requestId.current) setData(body) })
      .catch((err) => { if (id === requestId.current) { setData(null); setError(err) } })
      .finally(() => { if (id === requestId.current) setLoading(false) })
  }, [selection])

  // Deck cards by name, with copies. The avatar goes first when it has data.
  const deckCards = useMemo(() => {
    const byKey = new Map()
    if (avatarName) byKey.set(nameKey(avatarName), { name: avatarName, qty: 1 })
    for (const card of cards || []) {
      const key = nameKey(card.name)
      if (!key) continue
      const seen = byKey.get(key)
      const qty = card.qty ?? card.quantity ?? 1
      if (seen) seen.qty += qty
      else byKey.set(key, { name: card.name, qty })
    }
    return byKey
  }, [cards, avatarName])

  const allRows = data?.cards ?? []
  const deckRows = useMemo(
    () => allRows.filter((row) => deckCards.has(row.cardKey) || deckCards.has(nameKey(row.cardName))),
    [allRows, deckCards],
  )
  const missing = useMemo(() => {
    const found = new Set(deckRows.flatMap((row) => [row.cardKey, nameKey(row.cardName)]))
    return [...deckCards.entries()].filter(([key]) => !found.has(key)).map(([, card]) => card.name)
  }, [deckRows, deckCards])

  const catalogIndex = useMemo(() => indexCardMetadata(catalog), [catalog])
  const avatarImages = useMemo(
    () => new Map(catalog.filter((c) => c.type === 'Avatar').map((c) => [c.name.toLowerCase(), c.imageUrl])),
    [catalog],
  )
  const extraMetrics = useMemo(() => extraRateMetrics(deckRows), [deckRows])
  // A deck is at most ~60 distinct cards, so one page always fits.
  const table = useMemo(
    () => selectCardTable(deckRows, catalogIndex, NO_FILTERS, sortKey, sortDirection, 1),
    [deckRows, catalogIndex, sortKey, sortDirection],
  )

  const chooseSort = (key) => {
    if (key === sortKey) setSortDirection((d) => (d === 'ascending' ? 'descending' : 'ascending'))
    else {
      setSortKey(key)
      setSortDirection(key === 'cardName' ? 'ascending' : 'descending')
    }
  }

  const unavailable = error?.status === 503 || (data && data.dataAvailable === false)

  return (
    <div className="flex flex-col gap-3 mb-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-text-muted">Season
          <select value={season} onChange={(e) => setSeason(e.target.value)} className={`${FIELD} max-w-[300px]`}>
            <option value={ALL_SEASONS}>All released games</option>
            {seasons.map((s) => <option key={s.id} value={s.id}>{seasonLabel(s)}</option>)}
          </select>
        </label>
        <p className="text-xs text-text-muted" aria-live="polite">
          Each card across all Summit ranked games on Play Sorcery Online
          {data?.releasedThrough && <> {'·'} data through {data.releasedThrough}</>}
          {' · '}
          <Link to="/card-stats" className="text-primary hover:underline">All cards</Link>
        </p>
      </div>

      {loading ? (
        <Spinner className="py-10" />
      ) : unavailable ? (
        <p className="bg-bg-surface border border-border rounded-soft p-6 text-center text-sm text-text-muted">
          Card stats aren’t available right now. Play Sorcery Online publishes Summit ranked data in two-week batches.
        </p>
      ) : error ? (
        <p className="bg-bg-surface border border-border rounded-soft p-6 text-center text-sm text-text-muted">
          Couldn’t load card stats. Try again in a moment.
        </p>
      ) : deckRows.length === 0 ? (
        <p className="bg-bg-surface border border-border rounded-soft p-6 text-center text-sm text-text-muted">
          None of this deck’s cards have ranked games in this range yet.
        </p>
      ) : (
        <div className="bg-bg-surface border border-border rounded-soft overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-3 border-b border-border text-xs text-text-muted">
            <span role="status">{table.total} of {deckCards.size} cards in this deck have ranked data</span>
            <span>Click a column to sort. Click a card for art and replays.</span>
          </div>
          <CardWinRateTable
            rows={table.cards} sortKey={sortKey} sortDirection={sortDirection} onSort={chooseSort}
            selectedCard={selectedCard} onToggle={(key) => setSelectedCard((c) => (c === key ? null : key))}
            catalogIndex={catalogIndex} avatarImages={avatarImages} selection={selection}
            extraMetrics={extraMetrics}
          />
          <div className="px-4 sm:px-5 py-3 border-t border-border text-xs text-text-muted flex flex-col gap-1">
            <span>Rates hide below 20 player-games. A player-game is one player’s side of one game.</span>
            {missing.length > 0 && <span>No ranked data yet: {missing.join(', ')}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
