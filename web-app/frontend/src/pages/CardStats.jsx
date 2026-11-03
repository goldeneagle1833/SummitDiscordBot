import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getRankedCards, getRankedCatalog, getRankedSeasons, RANKED_ANALYTICS_ENDPOINT } from '@/api/rankedAnalytics'
import { get } from '@/api/client'
import { lookupCard, nameKey } from '@/components/analytics/format'
import CardPopularityChart from '@/components/analytics/CardPopularityChart'
import DataReleaseNote from '@/components/ui/DataReleaseNote'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import QuickFilters from '@/components/analytics/QuickFilters'
import ColumnMinimums from '@/components/analytics/ColumnMinimums'
import StandoutTiles from '@/components/analytics/StandoutTiles'
import CardWinRateTable, { extraRateMetrics } from '@/components/analytics/CardWinRateTable'
import { EMPTY_MINIMUMS, indexCardMetadata, minimumMetricValue, minimumSample, selectCardTable } from '@/vendor/analytics-ui/cardTable'
import { QueryBuilder } from '@/vendor/analytics-ui/QueryBuilder'
import '@/vendor/analytics-ui/summit-query.css'

const EMPTY_FILTERS = { type: '', element: '', rarity: '' }
const EMPTY_ROWS = []
const EMPTY_CATALOG = []

const TAB = 'px-4 min-h-[34px] rounded text-sm transition-colors'
const TAB_ON = `${TAB} bg-bg-elevated text-text`
const TAB_OFF = `${TAB} text-text-muted hover:text-text`
const FIELD = 'bg-bg-surface border border-border rounded px-3 text-sm text-text min-h-[36px] focus:outline-none focus:border-primary'
const GHOST = 'border border-border bg-bg-surface text-[#c9d1d9] rounded px-3 min-h-[32px] text-xs hover:border-primary/60 transition-colors'

// Summit only runs constructed ranked queues, so the format is fixed.
const FORMAT = 'constructed'

const ALL_SEASONS = 'all'
const CUSTOM_DATES = 'custom'

function selectionOf(from, through) {
  const selection = { format: FORMAT }
  if (from) selection.from = from
  if (through) selection.through = through
  return selection
}

const shortDay = (iso) => {
  if (!iso) return null
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function seasonLabel(season) {
  const range = season.through ? `${shortDay(season.from)} – ${shortDay(season.through)}` : `from ${shortDay(season.from)}`
  return `${season.name}${season.is_active ? ' (current)' : ''} · ${range}`
}

// Deck-usage numbers from Summit's own deck lists. Held as rate-shaped
// objects ({ winRate: value }) so the shared table code can sort them like
// any other column; the table shows them through each column's format.
const USAGE_COLUMNS = [
  { key: 'usageAvgCopies', label: 'Avg copies', position: 'lead', help: 'Average copies in decks that ran this card', format: (v) => v.toLocaleString() },
]
const MORE_USAGE_COLUMNS = [
  { key: 'infoElement', label: 'Element', text: true, help: 'Sort by element' },
  { key: 'infoType', label: 'Type', text: true, help: 'Sort by card type' },
  { key: 'infoRarity', label: 'Rarity', text: true, help: 'Sort by rarity' },
  { key: 'usageTotalCopies', label: 'Total copies', help: 'Copies across every reported deck', format: (v) => v.toLocaleString() },
  { key: 'usageCollection', label: 'Collection', help: 'Copies in decks’ collections', format: (v) => v.toLocaleString() },
  { key: 'usageDecksWith', label: 'Decks with', help: 'Reported decks that ran this card', format: (v) => v.toLocaleString() },
]
const NO_RATE = { playerGames: null, matches: null, wins: null, winRate: null, none: true }
const usageValue = (value) => (value == null ? null : { playerGames: null, matches: null, wins: null, winRate: value })

function usageFields(usage) {
  return {
    usageAvgCopies: usageValue(usage.average_played),
    usageTotalCopies: usageValue(usage.count),
    usageCollection: usageValue(usage.sideboard_count || 0),
    usageDecksWith: usageValue(usage.decks_with_card),
    usageInfo: { type: usage.type, element: usage.element, rarity: usage.rarity },
  }
}

const KNOWN = (value) => (value && value !== 'Unknown' && value !== 'None' ? value : '')

/**
 * Element / Type / Rarity as columns (Popular Cards had them). Each holds
 * { text, winRate: rank } so the shared sort orders them alphabetically,
 * blanks last.
 */
function withCardInfo(rows, catalogIndex) {
  const fields = [
    ['infoElement', (meta, info) => (meta?.elements?.length ? meta.elements.filter((e) => e && e !== 'None').join(' / ') : KNOWN(info?.element))],
    ['infoType', (meta, info) => meta?.type || KNOWN(info?.type)],
    ['infoRarity', (meta, info) => meta?.rarity || KNOWN(info?.rarity)],
  ]
  const texts = rows.map((row) => {
    const meta = lookupCard(catalogIndex, row)
    return fields.map(([, pick]) => pick(meta, row.usageInfo) || '')
  })
  const ranks = fields.map((_, i) => {
    const sorted = [...new Set(texts.map((t) => t[i]).filter(Boolean))].sort((a, b) => a.localeCompare(b))
    // Ranks run high to low so a descending sort reads A to Z.
    return new Map(sorted.map((text, index) => [text, sorted.length - index]))
  })
  return rows.map((row, r) => {
    const extra = {}
    fields.forEach(([key], i) => {
      const text = texts[r][i]
      extra[key] = { playerGames: null, matches: null, wins: null, winRate: text ? ranks[i].get(text) : null, text }
    })
    return { ...row, ...extra }
  })
}

/**
 * PSO rows with Summit's deck usage added. Popularity is Summit's own
 * "% of decks" (Bruce, 2026-11-03), so it never depends on PSO. Cards that
 * only Summit's deck lists have (older seasons, cards PSO hides) get a row
 * of their own with empty rates.
 */
function mergeRows(psoRows, usageRows) {
  if (!usageRows) return psoRows
  const usageByKey = new Map(usageRows.map((u) => [nameKey(u.name), u]))
  const seen = new Set()
  const merged = psoRows.map((row) => {
    const key = nameKey(row.cardName)
    const usage = usageByKey.get(key)
    seen.add(key)
    return usage
      ? { ...row, deckShare: usage.decks_with_card / usage.total_decks, ...usageFields(usage) }
      : { ...row, deckShare: null }
  })
  for (const [key, usage] of usageByKey) {
    if (seen.has(key)) continue
    merged.push({
      cardKey: `summit:${key}`, cardName: usage.name, summitOnly: true,
      deckShare: usage.decks_with_card / usage.total_decks,
      inDeck: NO_RATE, played: NO_RATE, openingHand: NO_RATE, inDeckUnplayed: NO_RATE,
      ...usageFields(usage),
    })
  }
  return merged
}

function UnavailablePanel({ title, children }) {
  return (
    <div className="bg-bg-surface border border-border rounded-soft p-8 text-center max-w-2xl mx-auto">
      <h2 className="font-display text-xl text-secondary mb-2">{title}</h2>
      <p className="text-sm text-text-muted">{children}</p>
    </div>
  )
}

/**
 * Card Stats: the old Card Win Rates and Popular Cards pages in one.
 *
 * Win rates come from Play Sorcery Online's Summit ranked analytics, saved on
 * Summit's side after each 1st/15th release (custom dates, the query
 * builder and replay clips still ask PSO). Popularity, copies and collection
 * counts come from the deck lists in Summit's own match records
 * (/api/creator/popular-cards), released in the same batches.
 */
export default function CardStats() {
  usePageTitle('Card Stats')

  const [tab, setTab] = useState('cards')
  const [seasons, setSeasons] = useState([])
  const [season, setSeason] = useState(ALL_SEASONS)
  const [from, setFrom] = useState('')
  const [through, setThrough] = useState('')
  const [search, setSearch] = useState('')
  const [quickFilters, setQuickFilters] = useState(EMPTY_FILTERS)
  const [minimums, setMinimums] = useState({ ...EMPTY_MINIMUMS })
  const [minimumValues, setMinimumValues] = useState({ ...EMPTY_MINIMUMS })
  const [minimumsOpen, setMinimumsOpen] = useState(false)
  const [sortKey, setSortKey] = useState('played')
  const [sortDirection, setSortDirection] = useState('descending')
  const [page, setPage] = useState(1)
  const [selectedCard, setSelectedCard] = useState(null)
  const [collectionOnly, setCollectionOnly] = useState(false)
  const [moreColumns, setMoreColumns] = useState(false)
  const [usage, setUsage] = useState(null)
  const [usageLoading, setUsageLoading] = useState(true)
  const usageRequestId = useRef(0)

  const [cards, setCards] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [catalog, setCatalog] = useState(EMPTY_CATALOG)
  const [catalogError, setCatalogError] = useState(null)
  const [queryPopulation, setQueryPopulation] = useState(null)
  const requestId = useRef(0)

  const chosenSeason = seasons.find((s) => s.id === season) ?? null
  const selection = useMemo(() => {
    if (season === CUSTOM_DATES) return selectionOf(from, through)
    if (chosenSeason) return selectionOf(chosenSeason.from, chosenSeason.through)
    return selectionOf('', '')
  }, [season, chosenSeason, from, through])
  const query = useMemo(() => new URLSearchParams(selection).toString(), [selection])
  const dateOrderProblem = season === CUSTOM_DATES && from && through && from > through

  useEffect(() => {
    getRankedSeasons()
      .then((rows) => setSeasons(Array.isArray(rows) ? rows : []))
      .catch(() => setSeasons([]))
  }, [])

  useEffect(() => {
    getRankedCatalog()
      .then((rows) => setCatalog(Array.isArray(rows) ? rows : EMPTY_CATALOG))
      .catch(() => setCatalogError('Card art and quick filters could not be loaded.'))
  }, [])

  useEffect(() => {
    if (dateOrderProblem) return
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    getRankedCards(selection)
      .then((body) => { if (id === requestId.current) setCards(body) })
      .catch((err) => { if (id === requestId.current) { setCards(null); setError(err) } })
      .finally(() => { if (id === requestId.current) setLoading(false) })
  }, [selection, dateOrderProblem])

  // Summit's own deck usage for the same season or dates. Never calls PSO.
  const usageQuery = useMemo(() => {
    const params = new URLSearchParams()
    if (season === CUSTOM_DATES) {
      if (from) params.set('from', from)
      if (through) params.set('through', through)
    } else if (season !== ALL_SEASONS) {
      params.set('event', season)
    }
    return params.toString()
  }, [season, from, through])

  useEffect(() => {
    if (dateOrderProblem) return
    const id = ++usageRequestId.current
    setUsageLoading(true)
    get(`/api/creator/popular-cards${usageQuery ? `?${usageQuery}` : ''}`)
      .then((body) => { if (id === usageRequestId.current) setUsage(Array.isArray(body) ? body : []) })
      .catch(() => { if (id === usageRequestId.current) setUsage(null) })
      .finally(() => { if (id === usageRequestId.current) setUsageLoading(false) })
  }, [usageQuery, dateOrderProblem])

  useEffect(() => {
    setPage(1)
    setSelectedCard(null)
  }, [selection, search, quickFilters, minimums, minimumValues, sortKey, sortDirection, collectionOnly])

  const catalogIndex = useMemo(() => indexCardMetadata(catalog), [catalog])
  const avatarImages = useMemo(
    () => new Map(catalog.filter((c) => c.type === 'Avatar').map((c) => [c.name.toLowerCase(), c.imageUrl])),
    [catalog],
  )
  const tableFilters = useMemo(
    () => ({ search, ...quickFilters, minimums, minimumValues }),
    [search, quickFilters, minimums, minimumValues],
  )
  const psoRows = cards?.dataAvailable === false ? EMPTY_ROWS : (cards?.cards ?? EMPTY_ROWS)
  // Extra PSO rate columns are read before the usage fields are added.
  const extraMetrics = useMemo(() => extraRateMetrics(psoRows), [psoRows])
  const mergedRows = useMemo(
    () => withCardInfo(mergeRows(psoRows, usage), catalogIndex),
    [psoRows, usage, catalogIndex],
  )
  const rows = useMemo(
    () => (collectionOnly ? mergedRows.filter((r) => r.usageCollection?.winRate) : mergedRows),
    [mergedRows, collectionOnly],
  )
  const usageColumns = moreColumns ? [...USAGE_COLUMNS, ...MORE_USAGE_COLUMNS] : USAGE_COLUMNS
  const psoMissing = psoRows.length === 0 && rows.length > 0
  const usageDecks = usage?.[0]?.total_decks ?? 0
  const table = useMemo(
    () => selectCardTable(rows, catalogIndex, tableFilters, sortKey, sortDirection, page),
    [rows, catalogIndex, tableFilters, sortKey, sortDirection, page],
  )

  const quickFilterCount = Object.values(quickFilters).filter(Boolean).length
  const minimumCount = Object.values(minimums).filter((v) => minimumSample(v) > 0).length
    + Object.values(minimumValues).filter((v) => minimumMetricValue(v) !== null).length
  const anyFilter = Boolean(search) || quickFilterCount > 0 || minimumCount > 0 || collectionOnly

  const clearFilters = () => {
    setCollectionOnly(false)
    setSearch('')
    setQuickFilters(EMPTY_FILTERS)
    setMinimums({ ...EMPTY_MINIMUMS })
    setMinimumValues({ ...EMPTY_MINIMUMS })
  }

  const chooseSort = (key) => {
    if (key === sortKey) {
      setSortDirection((d) => (d === 'ascending' ? 'descending' : 'ascending'))
    } else {
      setSortKey(key)
      setSortDirection(key === 'cardName' ? 'ascending' : 'descending')
    }
  }

  const jumpToCard = (cardKey) => {
    const index = selectCardTable(rows, catalogIndex, tableFilters, sortKey, sortDirection, 1)
    // Find which page the card lands on under the current sort, then open it there.
    const all = []
    for (let p = 1; p <= index.pageCount; p++) {
      all.push(...selectCardTable(rows, catalogIndex, tableFilters, sortKey, sortDirection, p).cards.map((c) => c.cardKey))
    }
    const position = all.indexOf(cardKey)
    if (position >= 0) setPage(Math.floor(position / 50) + 1)
    setSelectedCard(cardKey)
  }

  const receiveQueryPopulation = useCallback((key, data) => setQueryPopulation({ key, data }), [])
  const population = tab === 'query' && queryPopulation?.key === `${RANKED_ANALYTICS_ENDPOINT}?${query}`
    ? queryPopulation.data
    : cards

  // The page only gives up when neither PSO nor Summit's deck lists have rows.
  const unavailable = rows.length === 0 && !usage?.length
    && (error?.status === 503 || (cards && cards.dataAvailable === false))

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display text-secondary">Card Stats</h1>
          <p className="text-sm text-text-muted mt-1">
            How often each card shows up in Summit decks, and how often you win when it’s in your deck, in your opening hand, or gets played.
          </p>
          <p className="text-xs text-text-muted mt-1" aria-live="polite">
            {usageDecks > 0 && <>Popularity and copies from <span className="text-text">{usageDecks.toLocaleString()} reported decks</span> {'·'} </>}
            Win rates from Summit ranked games on Play Sorcery Online
            {population?.dataAvailable && typeof population.totalGames === 'number' && (
              <> {'·'} <span className="text-text">{population.totalGames.toLocaleString()} games</span></>
            )}
          </p>
          <DataReleaseNote className="mt-1" />
        </div>
        <div className="flex gap-1 bg-bg-surface border border-border rounded-lg p-1 self-start" role="tablist" aria-label="Analytics views">
          <button type="button" role="tab" aria-selected={tab === 'cards'} onClick={() => setTab('cards')} className={tab === 'cards' ? TAB_ON : TAB_OFF}>Cards</button>
          <button type="button" role="tab" aria-selected={tab === 'query'} onClick={() => setTab('query')} className={tab === 'query' ? TAB_ON : TAB_OFF}>Build a query</button>
        </div>
      </section>

      <section className="flex flex-col gap-3" aria-label="Data selection">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-text-muted">Season
            <select value={season} onChange={(e) => setSeason(e.target.value)} className={`${FIELD} max-w-[320px]`}>
              <option value={ALL_SEASONS}>All released games</option>
              {seasons.map((s) => (
                <option key={s.id} value={s.id}>{seasonLabel(s)}</option>
              ))}
              <option value={CUSTOM_DATES}>Custom dates…</option>
            </select>
          </label>
          {season === CUSTOM_DATES && (
            <>
              <label className="flex items-center gap-2 text-sm text-text-muted">From
                <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={FIELD} />
              </label>
              <label className="flex items-center gap-2 text-sm text-text-muted">Through
                <input type="date" value={through} onChange={(e) => setThrough(e.target.value)} className={FIELD} />
              </label>
            </>
          )}
          {tab === 'cards' && (
            <input
              type="search" aria-label="Search cards" placeholder="Search cards…"
              value={search} onChange={(e) => setSearch(e.target.value)}
              className={`${FIELD} w-full sm:w-64 sm:ml-auto placeholder:text-text-muted`}
            />
          )}
        </div>
        {dateOrderProblem && (
          <p className="text-xs text-accent-red" role="alert">The From date must be on or before the Through date.</p>
        )}
        {tab === 'cards' && (
          <div className="flex flex-wrap items-center gap-2">
            <QuickFilters filters={quickFilters} onChange={setQuickFilters} disabled={Boolean(catalogError)} />
            <button type="button" aria-pressed={collectionOnly} onClick={() => setCollectionOnly((v) => !v)}
              className={collectionOnly ? `${GHOST} !bg-primary !text-bg !border-primary` : GHOST}>
              Collection only
            </button>
            <div className="flex items-center gap-2 sm:ml-auto">
              <button type="button" aria-pressed={moreColumns} onClick={() => setMoreColumns((v) => !v)} className={GHOST}>
                {moreColumns ? 'Fewer columns' : 'More columns'}
              </button>
              {anyFilter && (
                <button type="button" onClick={clearFilters} className="text-xs text-primary hover:underline px-1 min-h-[32px]">Clear filters</button>
              )}
              <button type="button" aria-expanded={minimumsOpen} onClick={() => setMinimumsOpen((o) => !o)} className={GHOST}>
                Column minimums{minimumCount > 0 && <span className="ml-1 text-secondary">{minimumCount}</span>} {minimumsOpen ? '▾' : '▸'}
              </button>
            </div>
          </div>
        )}
        {tab === 'cards' && catalogError && <p className="text-xs text-text-muted">{catalogError}</p>}
        {tab === 'cards' && minimumsOpen && (
          <ColumnMinimums minimums={minimums} minimumValues={minimumValues} onMinimums={setMinimums} onMinimumValues={setMinimumValues} />
        )}
      </section>

      {tab === 'cards' ? (
        loading || usageLoading ? (
          <Spinner className="py-20" />
        ) : unavailable ? (
          <UnavailablePanel title="Ranked analytics isn’t available yet">
            Play Sorcery Online publishes Summit ranked card data in two-week batches.
            Check back soon.
          </UnavailablePanel>
        ) : error && rows.length === 0 ? (
          <UnavailablePanel title="Couldn’t load card analytics">
            {error.message || 'Something went wrong. Try again in a moment.'}
          </UnavailablePanel>
        ) : rows.length === 0 ? (
          <UnavailablePanel title="No games in this range">
            No Summit ranked games were released for this date range yet.
          </UnavailablePanel>
        ) : (
          <>
            {psoMissing && (
              <p className="text-xs text-text-muted bg-bg-surface border border-border rounded-soft px-4 py-3">
                Play Sorcery Online has no win-rate data for this selection, so only popularity and copies from Summit’s deck lists are shown.
              </p>
            )}
            {usage === null && (
              <p className="text-xs text-text-muted bg-bg-surface border border-border rounded-soft px-4 py-3">
                Summit’s deck-usage numbers couldn’t be loaded, so Popularity and copies are blank. Try again in a moment.
              </p>
            )}
            <StandoutTiles cards={rows} catalogIndex={catalogIndex} filters={tableFilters} onSelect={jumpToCard} />
            <div className="bg-bg-surface border border-border rounded-soft overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-3 border-b border-border text-xs text-text-muted">
                <span role="status">
                  {table.total
                    ? `Showing ${table.start.toLocaleString()}–${table.end.toLocaleString()} of ${table.total.toLocaleString()} cards`
                    : 'No cards match these filters'}
                </span>
                <span>Click any column header to sort. Click a card for art and replays.</span>
              </div>
              {table.total === 0 ? (
                <p className="text-center text-text-muted py-10 text-sm">No cards match this selection. Try fewer filters.</p>
              ) : (
                <CardWinRateTable
                  rows={table.cards} sortKey={sortKey} sortDirection={sortDirection} onSort={chooseSort}
                  selectedCard={selectedCard} onToggle={(key) => setSelectedCard((c) => (c === key ? null : key))}
                  catalogIndex={catalogIndex} avatarImages={avatarImages} selection={selection}
                  extraMetrics={extraMetrics} usageColumns={usageColumns}
                  detailExtra={(card) => <CardPopularityChart cardName={card.cardName} />}
                />
              )}
              <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-3 border-t border-border text-xs text-text-muted">
                <span>Rates hide below 20 player-games. A player-game is one player’s side of one game. Popularity counts reported Summit decks.</span>
                {table.pageCount > 1 && (
                  <nav className="flex items-center gap-2" aria-label="Card pages">
                    <button type="button" disabled={table.page <= 1} onClick={() => { setPage(table.page - 1); setSelectedCard(null) }} className={`${GHOST} disabled:opacity-40`}>← Previous</button>
                    <span>Page {table.page} of {table.pageCount}</span>
                    <button type="button" disabled={table.page >= table.pageCount} onClick={() => { setPage(table.page + 1); setSelectedCard(null) }} className={`${GHOST} disabled:opacity-40`}>Next →</button>
                  </nav>
                )}
              </div>
            </div>
          </>
        )
      ) : (
        <QueryBuilder
          endpoint={RANKED_ANALYTICS_ENDPOINT} query={query} admin={false} active={tab === 'query'}
          catalog={catalog} catalogError={catalogError} onPopulation={receiveQueryPopulation}
        />
      )}
    </div>
  )
}
