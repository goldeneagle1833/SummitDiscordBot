import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRankedCards, getRankedCatalog, getRankedSeasons } from '@/api/rankedAnalytics'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import DataReleaseNote from '@/components/ui/DataReleaseNote'
import CardPopularityChart from '@/components/analytics/CardPopularityChart'
import { CardReplays, EffectCell, StatCard, extraRateMetrics } from '@/components/analytics/CardWinRateTable'
import { nameKey, percent } from '@/components/analytics/format'

// Summit only runs constructed ranked queues, so the format is fixed.
const FORMAT = 'constructed'
const ALL_SEASONS = 'all'
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

function NumberTile({ label, value, note, highlight }) {
  return (
    <div className={`bg-bg-surface border rounded-soft p-3 flex flex-col gap-1 ${highlight ? 'border-secondary' : 'border-border'}`}>
      <span className={`text-[11px] ${highlight ? 'text-secondary' : 'text-text-muted'}`}>{label}</span>
      <span className="text-xl font-bold text-text">{value ?? '—'}</span>
      {note && <span className="text-[11px] text-text-muted">{note}</span>}
    </div>
  )
}

/**
 * Everything the Card Stats page knows about one card, for the card page.
 *
 * Win rates come from /api/ranked-analytics/cards for all released games or
 * one season. Those selections are served from Summit's saved copy of the
 * PSO data (refreshed once per 1st/15th release), so a visit never asks Play
 * Sorcery Online live. There are no custom dates here for that reason.
 * Popularity and copies come from Summit's own deck lists
 * (/api/creator/popular-cards). Replay clips are the one live PSO call, and
 * they load only when the visitor asks for them.
 */
export default function CardRankedStats({ cardName }) {
  const [seasons, setSeasons] = useState([])
  const [season, setSeason] = useState(ALL_SEASONS)
  const [catalog, setCatalog] = useState([])
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [usage, setUsage] = useState(null)
  const [usageLoading, setUsageLoading] = useState(true)
  const requestId = useRef(0)
  const usageRequestId = useRef(0)

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
    getRankedCards(selection)
      .then((body) => { if (id === requestId.current) setData(body) })
      .catch((err) => { if (id === requestId.current) { setData(null); setError(err) } })
      .finally(() => { if (id === requestId.current) setLoading(false) })
  }, [selection])

  useEffect(() => {
    const id = ++usageRequestId.current
    setUsageLoading(true)
    const query = season === ALL_SEASONS ? '' : `?${new URLSearchParams({ event: season })}`
    get(`/api/creator/popular-cards${query}`)
      .then((body) => { if (id === usageRequestId.current) setUsage(Array.isArray(body) ? body : []) })
      .catch(() => { if (id === usageRequestId.current) setUsage(null) })
      .finally(() => { if (id === usageRequestId.current) setUsageLoading(false) })
  }, [season])

  const key = nameKey(cardName)
  const allRows = data?.dataAvailable === false ? [] : (data?.cards ?? [])
  const row = useMemo(
    () => allRows.find((r) => r.cardKey === key || nameKey(r.cardName) === key) ?? null,
    [allRows, key],
  )
  const extraMetrics = useMemo(() => extraRateMetrics(allRows), [allRows])

  const usageSorted = useMemo(
    () => (usage ? [...usage].sort((a, b) => b.decks_with_card - a.decks_with_card) : []),
    [usage],
  )
  const usageIndex = usageSorted.findIndex((u) => nameKey(u.name) === key)
  const cardUsage = usageIndex >= 0 ? usageSorted[usageIndex] : null
  const totalDecks = cardUsage?.total_decks ?? usage?.[0]?.total_decks ?? 0

  const avatarImages = useMemo(
    () => new Map(catalog.filter((c) => c.type === 'Avatar').map((c) => [c.name.toLowerCase(), c.imageUrl])),
    [catalog],
  )

  const pso503 = error?.status === 503 || data?.dataAvailable === false

  return (
    <div className="bg-bg-surface border border-border rounded-soft p-5 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-text-primary">Ranked Card Stats</h2>
          <p className="text-xs text-text-muted mt-1">
            Win rates from Summit ranked games on Play Sorcery Online
            {totalDecks > 0 && <> {'·'} popularity from {totalDecks.toLocaleString()} reported decks</>}
            {' · '}
            <Link to="/card-stats" className="text-primary hover:underline">All cards</Link>
          </p>
          <DataReleaseNote className="mt-1" />
        </div>
        <label className="flex items-center gap-2 text-sm text-text-muted min-w-0">Season
          <select value={season} onChange={(e) => setSeason(e.target.value)} className={`${FIELD} min-w-0 w-full sm:w-auto sm:max-w-[300px]`}>
            <option value={ALL_SEASONS}>All released games</option>
            {seasons.map((s) => <option key={s.id} value={s.id}>{seasonLabel(s)}</option>)}
          </select>
        </label>
      </div>

      {loading || usageLoading ? (
        <Spinner className="py-10" />
      ) : (
        <>
          <section aria-label="Popularity" className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Popularity</h3>
            {cardUsage ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <NumberTile
                  label="Popularity" highlight
                  value={percent(cardUsage.decks_with_card / cardUsage.total_decks, 1)}
                  note={`#${(usageIndex + 1).toLocaleString()} of ${usageSorted.length.toLocaleString()} cards`}
                />
                <NumberTile label="Decks with" value={cardUsage.decks_with_card.toLocaleString()} note={`of ${cardUsage.total_decks.toLocaleString()} decks`} />
                <NumberTile label="Avg copies" value={cardUsage.average_played.toLocaleString()} note="in decks that ran it" />
                <NumberTile label="Total copies" value={cardUsage.count.toLocaleString()} note="across every deck" />
                <NumberTile label="Collection" value={(cardUsage.sideboard_count || 0).toLocaleString()} note="copies in collections" />
              </div>
            ) : (
              <p className="text-xs text-text-muted">
                {usage === null
                  ? 'Summit’s deck-usage numbers couldn’t be loaded. Try again in a moment.'
                  : 'No reported Summit decks ran this card in this selection.'}
              </p>
            )}
          </section>

          <section aria-label="Win rates" className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Win rates</h3>
            {pso503 ? (
              <p className="text-xs text-text-muted">
                Win rates aren’t available for this selection. Play Sorcery Online publishes Summit ranked data in two-week batches.
              </p>
            ) : error ? (
              <p className="text-xs text-text-muted">Couldn’t load win rates. Try again in a moment.</p>
            ) : !row ? (
              <p className="text-xs text-text-muted">No Summit ranked games on Play Sorcery Online have this card in this selection yet.</p>
            ) : (
              <>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  <StatCard label="In deck" rate={row.inDeck} barTone="bg-primary" />
                  <StatCard label="Played" rate={row.played} highlight />
                  <StatCard label="In opening hand" rate={row.openingHand} barTone="bg-primary" />
                  {extraMetrics.map(({ key: metric, label }) => (
                    row[metric] ? <StatCard key={metric} label={label} rate={row[metric]} barTone="bg-primary" /> : null
                  ))}
                  <StatCard label="In deck, never played" rate={row.inDeckUnplayed} barTone="bg-text-muted" />
                  <div className="bg-bg-surface border border-border rounded-soft p-3 col-span-2 lg:col-span-1 flex flex-col gap-1.5">
                    <span className="text-[11px] text-text-muted">Effect of playing it</span>
                    <div className="text-lg sm:text-xl"><EffectCell card={row} /></div>
                    <span className="text-[11px] text-text-muted">Played minus in deck, never played</span>
                  </div>
                </div>
                <p className="text-[11px] text-text-muted">Rates hide below 20 player-games. A player-game is one player’s side of one game.</p>
              </>
            )}
          </section>

          {row && !pso503 && (
            <CardReplays cardKey={row.cardKey} selection={selection} avatarImages={avatarImages} onDemand />
          )}
        </>
      )}

      <CardPopularityChart cardName={cardName} showCardLink={false} />
    </div>
  )
}
