import { useMemo } from 'react'
import { cardMetricValue, selectCardTable } from '@/vendor/analytics-ui/cardTable'
import { lookupCard, percent, ppLabel, TONE_TEXT, winRateTone } from './format'

function CardThumb({ card, catalogIndex }) {
  const meta = lookupCard(catalogIndex, card)
  return meta?.imageUrl ? (
    <img src={meta.imageUrl} alt="" loading="lazy" className="w-10 h-14 object-cover rounded flex-shrink-0" />
  ) : (
    <div className="w-10 h-14 rounded bg-bg-elevated flex-shrink-0" aria-hidden="true" />
  )
}

/**
 * Four headline cards drawn from whatever the current filters match, so the
 * tiles always agree with the table underneath them.
 */
export default function StandoutTiles({ cards, catalogIndex, filters, onSelect }) {
  const tiles = useMemo(() => {
    const first = (sortKey, direction) =>
      selectCardTable(cards, catalogIndex, filters, sortKey, direction, 1).cards[0] ?? null
    const played = first('played', 'descending')
    const popular = first('deckShare', 'descending')
    const swing = first('winRateDifference', 'descending')
    const weakest = first('played', 'ascending')
    return [
      played && {
        key: 'best', label: 'Best when played', card: played,
        value: percent(played.played.winRate), tone: winRateTone(played.played.winRate),
        detail: `${played.played.playerGames?.toLocaleString()} games`,
      },
      popular && {
        key: 'popular', label: 'Most played', card: popular,
        value: `${percent(popular.deckShare, 0)} of decks`, tone: 'accent',
        detail: `${popular.inDeck.playerGames?.toLocaleString()} games`,
      },
      swing && {
        key: 'swing', label: 'Biggest swing', card: swing,
        value: ppLabel(cardMetricValue(swing, 'winRateDifference')), tone: 'good',
        detail: 'played vs. not played',
      },
      weakest && {
        key: 'weak', label: 'Underperforming', card: weakest,
        value: percent(weakest.played.winRate), tone: winRateTone(weakest.played.winRate),
        detail: `${ppLabel(cardMetricValue(weakest, 'winRateDifference'))} when played`,
      },
    ].filter(Boolean)
  }, [cards, catalogIndex, filters])

  if (tiles.length === 0) return null

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" aria-label="Standout cards">
      {tiles.map((tile) => (
        <button
          key={tile.key}
          type="button"
          onClick={() => onSelect(tile.card.cardKey)}
          className="flex items-center gap-3 bg-bg-surface border border-border rounded-soft p-3 text-left hover:border-primary/60 transition-colors"
        >
          <CardThumb card={tile.card} catalogIndex={catalogIndex} />
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wider text-text-muted">{tile.label}</div>
            <div className="text-sm font-semibold truncate">{tile.card.cardName}</div>
            <div className={`text-sm font-bold ${tile.tone === 'accent' ? 'text-primary' : TONE_TEXT[tile.tone]}`}>
              {tile.value} <span className="font-normal text-text-muted text-xs">· {tile.detail}</span>
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}
