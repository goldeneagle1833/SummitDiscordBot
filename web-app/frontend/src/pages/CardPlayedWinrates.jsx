import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getRankedCards, getRankedCatalog, RANKED_ANALYTICS_ENDPOINT } from '@/api/rankedAnalytics'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import QuickFilters from '@/components/analytics/QuickFilters'
import ColumnMinimums from '@/components/analytics/ColumnMinimums'
import StandoutTiles from '@/components/analytics/StandoutTiles'
import CardWinRateTable from '@/components/analytics/CardWinRateTable'
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

function selectionOf(from, through) {
  const selection = { format: FORMAT }
  if (from) selection.from = from
  if (through) selection.through = through
  return selection
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
 * Card Win Rates, fed by Play Sorcery Online's Summit ranked analytics.
 *
 * Every rate comes from PSO through the server-side proxy. The population is
 * fixed there: first games at Summit matchmade ranked tables, released in
 * batches on the 1st and 15th. This page filters, sorts and pages those
 * rows in the browser and never re-computes a rate itself.
 */
export default function CardPlayedWinrates() {
  usePageTitle('Card Win Rates')

  const [tab, setTab] = useState('cards')
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

  const [cards, setCards] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [catalog, setCatalog] = useState(EMPTY_CATALOG)
  const [catalogError, setCatalogError] = useState(null)
  const [queryPopulation, setQueryPopulation] = useState(null)
  const requestId = useRef(0)

  const selection = useMemo(() => selectionOf(from, through), [from, through])
  const query = useMemo(() => new URLSearchParams(selection).toString(), [selection])
  const dateOrderProblem = from && through && from > through

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

  useEffect(() => {
    setPage(1)
    setSelectedCard(null)
  }, [selection, search, quickFilters, minimums, minimumValues, sortKey, sortDirection])

  const catalogIndex = useMemo(() => indexCardMetadata(catalog), [catalog])
  const avatarImages = useMemo(
    () => new Map(catalog.filter((c) => c.type === 'Avatar').map((c) => [c.name.toLowerCase(), c.imageUrl])),
    [catalog],
  )
  const tableFilters = useMemo(
    () => ({ search, ...quickFilters, minimums, minimumValues }),
    [search, quickFilters, minimums, minimumValues],
  )
  const rows = cards?.cards ?? EMPTY_ROWS
  const table = useMemo(
    () => selectCardTable(rows, catalogIndex, tableFilters, sortKey, sortDirection, page),
    [rows, catalogIndex, tableFilters, sortKey, sortDirection, page],
  )

  const quickFilterCount = Object.values(quickFilters).filter(Boolean).length
  const minimumCount = Object.values(minimums).filter((v) => minimumSample(v) > 0).length
    + Object.values(minimumValues).filter((v) => minimumMetricValue(v) !== null).length
  const anyFilter = Boolean(search) || quickFilterCount > 0 || minimumCount > 0

  const clearFilters = () => {
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

  const unavailable = error?.status === 503 || (cards && cards.dataAvailable === false)

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display text-secondary">Card Win Rates</h1>
          <p className="text-sm text-text-muted mt-1">
            When a card is in your deck, in your opening hand, or gets played, how often do you win?
          </p>
          <p className="text-xs text-text-muted mt-1" aria-live="polite">
            Summit ranked games on Play Sorcery Online
            {population?.dataAvailable && typeof population.totalGames === 'number' && (
              <> {'·'} <span className="text-text">{population.totalGames.toLocaleString()} games</span></>
            )}
            {population?.releasedThrough && <> {'·'} data through {population.releasedThrough}</>}
          </p>
        </div>
        <div className="flex gap-1 bg-bg-surface border border-border rounded-lg p-1 self-start" role="tablist" aria-label="Analytics views">
          <button type="button" role="tab" aria-selected={tab === 'cards'} onClick={() => setTab('cards')} className={tab === 'cards' ? TAB_ON : TAB_OFF}>Cards</button>
          <button type="button" role="tab" aria-selected={tab === 'query'} onClick={() => setTab('query')} className={tab === 'query' ? TAB_ON : TAB_OFF}>Build a query</button>
        </div>
      </section>

      <section className="flex flex-col gap-3" aria-label="Data selection">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-text-muted">From
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={FIELD} />
          </label>
          <label className="flex items-center gap-2 text-sm text-text-muted">Through
            <input type="date" value={through} onChange={(e) => setThrough(e.target.value)} className={FIELD} />
          </label>
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
            <div className="flex items-center gap-2 sm:ml-auto">
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
        loading ? (
          <Spinner className="py-20" />
        ) : unavailable ? (
          <UnavailablePanel title="Ranked analytics isn’t available yet">
            Play Sorcery Online publishes Summit ranked card data in batches on the 1st and 15th of each month.
            Check back soon.
          </UnavailablePanel>
        ) : error ? (
          <UnavailablePanel title="Couldn’t load card analytics">
            {error.message || 'Something went wrong. Try again in a moment.'}
          </UnavailablePanel>
        ) : rows.length === 0 ? (
          <UnavailablePanel title="No games in this range">
            No Summit ranked games were released for this date range yet.
          </UnavailablePanel>
        ) : (
          <>
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
                />
              )}
              <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-3 border-t border-border text-xs text-text-muted">
                <span>Rates hide below 20 player-games. A player-game is one player’s side of one game.</span>
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
