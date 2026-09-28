import { Fragment, useEffect, useState } from 'react'
import { getRankedCardReplays } from '@/api/rankedAnalytics'
import { CARD_METRICS, cardMetricValue } from '@/vendor/analytics-ui/cardTable'
import { gamesLabel, lookupCard, percent, ppLabel, shortDate, TONE_BAR, TONE_TEXT, winRateTone } from './format'

export const REPLAY_CLIP_BASE = 'https://playsorceryonline.com/replay-clips/'

const LEADING_COLUMNS = [
  { key: 'cardName', label: 'Card' },
  { key: 'deckShare', label: 'Popularity' },
  { key: 'inDeck', label: 'In deck' },
  { key: 'played', label: 'Played' },
  { key: 'openingHand', label: 'Opening hand' },
]
const TRAILING_COLUMNS = [
  { key: 'inDeckUnplayed', label: 'Not played' },
  { key: 'winRateDifference', label: 'Effect of playing it' },
]
const BUILT_IN_KEYS = new Set([...LEADING_COLUMNS, ...TRAILING_COLUMNS].map((c) => c.key))

const COLUMN_HELP = {
  cardName: 'Sort by card name',
  deckShare: 'Share of decks that ran this card',
  inDeck: 'Win rate of players who had it in their deck',
  played: 'Win rate of players who played it',
  openingHand: 'Win rate when it was in the post-mulligan opening hand',
  inDeckUnplayed: 'Win rate when it was in the deck but never played',
  winRateDifference: 'Played win rate minus in-deck, not-played win rate (percentage points)',
}

// Labels for rate columns PSO has added or may add. Anything else gets a
// humanized version of its key.
const EXTRA_LABELS = {
  inHand: 'In hand',
  notInHand: 'Not in hand',
  inDeckNotInHand: 'Not in hand',
  drawn: 'Drawn',
  notDrawn: 'Not drawn',
}

const humanize = (key) => {
  const words = key.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/**
 * Rate columns present on the rows beyond the ones this table was built
 * for, in the order PSO sends them. Any object with a winRate counts.
 */
export function extraRateMetrics(rows) {
  const first = rows[0]
  if (!first) return []
  return Object.keys(first)
    .filter((key) => !BUILT_IN_KEYS.has(key) && first[key] && typeof first[key] === 'object' && 'winRate' in first[key])
    .map((key) => ({ key, label: EXTRA_LABELS[key] ?? humanize(key) }))
}

export function tableColumns(extraMetrics = []) {
  return [...LEADING_COLUMNS, ...extraMetrics, ...TRAILING_COLUMNS]
}

const columnHelp = (column) =>
  COLUMN_HELP[column.key] ?? `Win rate when the card was ${column.label.toLowerCase()}`

// The diverging bar caps at 20 pp either way.
const BAR_CAP = 0.2

function RateCell({ rate }) {
  const tone = winRateTone(rate.winRate)
  return (
    <div className="flex flex-col leading-tight">
      <span className={`font-semibold ${TONE_TEXT[tone]}`}>{percent(rate.winRate)}</span>
      <span className="text-[11px] text-text-muted">{gamesLabel(rate.playerGames)}</span>
    </div>
  )
}

function EffectCell({ card }) {
  const difference = cardMetricValue(card, 'winRateDifference')
  if (difference == null) return <span className="text-text-muted">—</span>
  const width = Math.min(50, (Math.abs(difference) / BAR_CAP) * 50)
  const positive = difference >= 0
  return (
    <div className="flex items-center gap-2.5">
      <div className="relative w-[90px] h-2 rounded bg-bg-elevated flex-shrink-0" aria-hidden="true">
        <div
          className={`absolute top-0 h-2 ${positive ? 'left-1/2 rounded-r bg-[#3fb950]' : 'right-1/2 rounded-l bg-[#f85149]'}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className={`font-bold ${positive ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>{ppLabel(difference)}</span>
    </div>
  )
}

function AvatarPortrait({ name, imageUrl, won }) {
  const ring = won == null ? 'border-border' : won ? 'border-[#3fb950]' : 'border-[#f85149]'
  return imageUrl ? (
    <img src={imageUrl} alt={name} title={name} loading="lazy"
      className={`w-8 h-8 rounded-full object-cover object-[50%_20%] border-2 ${ring}`} />
  ) : (
    <span role="img" aria-label={name} title={name}
      className={`w-8 h-8 rounded-full bg-bg-elevated border-2 ${ring} flex items-center justify-center text-[10px] text-text-muted`}>
      {name.slice(0, 2)}
    </span>
  )
}

function ReplayLink({ replay, avatarImages }) {
  const player = replay.player?.avatarNames?.[0] ?? 'Unknown avatar'
  const opponent = replay.opponent?.avatarNames?.[0] ?? 'Unknown avatar'
  return (
    <a
      href={`${REPLAY_CLIP_BASE}${encodeURIComponent(replay.clipId)}`}
      target="_blank" rel="noreferrer"
      title="Opens on Play Sorcery Online one step before the play. Result is for the card player, shown on the left."
      className="flex items-center gap-2.5 bg-bg-base border border-border rounded-soft px-3 py-2 hover:border-primary/60 transition-colors"
    >
      <span className="flex items-center gap-1.5">
        <AvatarPortrait name={player} imageUrl={avatarImages.get(player.toLowerCase())} won={replay.won} />
        <span className="text-[11px] text-text-muted">vs</span>
        <AvatarPortrait name={opponent} imageUrl={avatarImages.get(opponent.toLowerCase())} won={null} />
      </span>
      <span className="flex flex-col flex-1 min-w-0 leading-tight">
        <span className="text-xs font-semibold">{replay.won ? 'Win' : 'Loss'} · {shortDate(replay.finishedAt)}</span>
        <span className="text-[11px] text-text-muted truncate">{player} vs. {opponent}</span>
      </span>
      <span className="text-xs text-primary whitespace-nowrap">Watch ↗</span>
    </a>
  )
}

function StatCard({ label, rate, highlight, barTone }) {
  const tone = winRateTone(rate.winRate)
  return (
    <div className={`bg-bg-surface border rounded-soft p-3 flex flex-col gap-1.5 ${highlight ? 'border-secondary' : 'border-border'}`}>
      <span className={`text-[11px] ${highlight ? 'text-secondary' : 'text-text-muted'}`}>{label}</span>
      <span className={`text-xl font-bold ${TONE_TEXT[tone]}`}>{percent(rate.winRate)}</span>
      <div className="h-1.5 rounded bg-bg-elevated" aria-hidden="true">
        {rate.winRate != null && (
          <div className={`h-1.5 rounded ${barTone ?? TONE_BAR[tone]}`} style={{ width: `${rate.winRate * 100}%` }} />
        )}
      </div>
      <span className="text-[11px] text-text-muted">{rate.playerGames == null ? 'under 20 player-games' : `${rate.playerGames.toLocaleString()} player-games`}</span>
    </div>
  )
}

function CardDetailRow({ card, meta, selection, avatarImages, extraMetrics, columnCount }) {
  const [replays, setReplays] = useState({ loading: true, error: null, items: [] })

  useEffect(() => {
    let cancelled = false
    setReplays({ loading: true, error: null, items: [] })
    getRankedCardReplays(card.cardKey, selection)
      .then((body) => { if (!cancelled) setReplays({ loading: false, error: null, items: body.replays ?? [] }) })
      .catch(() => { if (!cancelled) setReplays({ loading: false, error: 'Public replays could not be loaded.', items: [] }) })
    return () => { cancelled = true }
  }, [card.cardKey, selection])

  const details = [meta?.type, meta?.elements?.length ? meta.elements.join(' / ') : null, meta?.rarity].filter(Boolean)

  return (
    <tr className="bg-bg-base">
      <td colSpan={columnCount} className="px-4 sm:px-5 py-5 border-b border-border">
        <div className="flex flex-col md:flex-row gap-5 items-start">
          {meta?.imageUrl ? (
            <img src={meta.imageUrl} alt={card.cardName} loading="lazy"
              className="w-40 sm:w-48 rounded-soft border border-border flex-shrink-0" />
          ) : (
            <div className="w-40 sm:w-48 aspect-[2.5/3.5] rounded-soft border border-border bg-bg-elevated flex items-center justify-center text-xs text-text-muted flex-shrink-0">
              Card art unavailable
            </div>
          )}
          <div className="flex-1 min-w-0 flex flex-col gap-4">
            <div className="flex flex-wrap items-baseline gap-3">
              <h3 className="font-display text-xl text-secondary">{card.cardName}</h3>
              {details.length > 0 && <span className="text-xs text-text-muted">{details.join(' · ')}</span>}
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCard label="In deck" rate={card.inDeck} barTone="bg-primary" />
              <StatCard label="Played" rate={card.played} highlight />
              <StatCard label="In opening hand" rate={card.openingHand} barTone="bg-primary" />
              {extraMetrics.map(({ key, label }) => (
                <StatCard key={key} label={label} rate={card[key]} barTone="bg-primary" />
              ))}
              <StatCard label="In deck, never played" rate={card.inDeckUnplayed} barTone="bg-text-muted" />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold">Watch it get played</span>
                <span className="text-[11px] text-text-muted">Public replays on Play Sorcery Online · opens just before the play</span>
              </div>
              {replays.loading ? (
                <p className="text-xs text-text-muted" role="status">Loading public replays…</p>
              ) : replays.error ? (
                <p className="text-xs text-text-muted" role="alert">{replays.error}</p>
              ) : replays.items.length === 0 ? (
                <p className="text-xs text-text-muted">No public replays are available for this selection.</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">
                  {replays.items.map((replay) => (
                    <ReplayLink key={replay.clipId} replay={replay} avatarImages={avatarImages} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </td>
    </tr>
  )
}

/**
 * The analytics table. Card names expand into a detail row with art, the
 * four rates as cards, and public replay clips. Scrolls sideways on phones
 * with the card column pinned.
 */
export default function CardWinRateTable({
  rows, sortKey, sortDirection, onSort, selectedCard, onToggle, catalogIndex, avatarImages, selection, extraMetrics = [],
}) {
  const columns = tableColumns(extraMetrics)
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs text-text-muted">
            {columns.map((column) => {
              const { key, label } = column
              const active = sortKey === key
              return (
                <th key={key} scope="col" aria-sort={active ? sortDirection : 'none'}
                  className={`px-3 first:px-4 first:sm:px-5 py-2.5 font-medium border-b border-border ${key === 'cardName' ? 'sticky left-0 bg-bg-surface z-10 min-w-[220px]' : ''}`}>
                  <button type="button" onClick={() => onSort(key)} title={columnHelp(column)}
                    className={`inline-flex items-center gap-1.5 hover:text-text ${active ? 'text-secondary' : ''}`}>
                    {label}
                    <span aria-hidden="true" className="text-[10px]">{active ? (sortDirection === 'ascending' ? '↑' : '↓') : '↕'}</span>
                  </button>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((card) => {
            const expanded = selectedCard === card.cardKey
            const meta = lookupCard(catalogIndex, card)
            return (
              <Fragment key={card.cardKey}>
                <tr className={`border-b border-border/50 transition-colors ${expanded ? 'bg-bg-elevated/60' : 'hover:bg-bg-elevated/40'}`}>
                  <th scope="row" className={`px-4 sm:px-5 py-2.5 font-normal text-left sticky left-0 z-10 ${expanded ? 'bg-[#1c2128]' : 'bg-bg-surface'}`}>
                    <button type="button" aria-expanded={expanded} onClick={() => onToggle(card.cardKey)}
                      className="flex items-center gap-2.5 text-left group">
                      <span aria-hidden="true" className={`text-xs ${expanded ? 'text-secondary' : 'text-text-muted'}`}>{expanded ? '▾' : '▸'}</span>
                      {meta?.imageUrl ? (
                        <img src={meta.imageUrl} alt="" loading="lazy" className="w-8 h-11 object-cover rounded flex-shrink-0" />
                      ) : (
                        <span aria-hidden="true" className="w-8 h-11 rounded bg-bg-elevated flex-shrink-0" />
                      )}
                      <span className={`font-semibold group-hover:text-primary ${expanded ? 'text-secondary' : ''}`}>{card.cardName}</span>
                    </button>
                  </th>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-2 rounded bg-bg-elevated" aria-hidden="true">
                        {card.deckShare != null && (
                          <div className="h-2 rounded bg-summit" style={{ width: `${Math.min(100, card.deckShare * 200)}%` }} />
                        )}
                      </div>
                      <span className="text-[#c9d1d9]">{percent(card.deckShare, 0)}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5"><RateCell rate={card.inDeck} /></td>
                  <td className="px-3 py-2.5"><RateCell rate={card.played} /></td>
                  <td className="px-3 py-2.5"><RateCell rate={card.openingHand} /></td>
                  {extraMetrics.map(({ key }) => (
                    <td key={key} className="px-3 py-2.5">
                      {card[key] ? <RateCell rate={card[key]} /> : <span className="text-text-muted">—</span>}
                    </td>
                  ))}
                  <td className="px-3 py-2.5"><RateCell rate={card.inDeckUnplayed} /></td>
                  <td className="px-3 py-2.5"><EffectCell card={card} /></td>
                </tr>
                {expanded && (
                  <CardDetailRow card={card} meta={meta} selection={selection} avatarImages={avatarImages}
                    extraMetrics={extraMetrics} columnCount={columns.length} />
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export { CARD_METRICS }
