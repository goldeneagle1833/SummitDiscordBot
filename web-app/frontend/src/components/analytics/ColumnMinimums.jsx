import { Fragment } from 'react'
import { CARD_METRICS } from '@/vendor/analytics-ui/cardTable'

const LABELS = {
  deckShare: 'Popularity',
  inDeck: 'In deck',
  played: 'Played',
  openingHand: 'Opening hand',
  inDeckUnplayed: 'Not played',
  winRateDifference: 'Effect of playing it',
}

const INPUT = 'w-full bg-bg-base border border-border rounded px-2 py-1.5 text-sm text-text min-h-[36px] focus:outline-none focus:border-primary'

/**
 * Per-column sample-size and value floors. Values are percentages, or
 * percentage points for the played-vs-not-played difference.
 */
export default function ColumnMinimums({ minimums, minimumValues, onMinimums, onMinimumValues }) {
  const setMinimum = (key, value) => {
    if (value === '' || /^\d+$/.test(value)) onMinimums({ ...minimums, [key]: value })
  }
  return (
    <div className="bg-bg-surface border border-border rounded-soft p-4 max-w-xl" role="group" aria-label="Column minimums">
      <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-x-3 gap-y-2 items-center">
        <span className="text-xs text-text-muted border-b border-border pb-1">Column</span>
        <span className="text-xs text-text-muted border-b border-border pb-1">Min. games</span>
        <span className="text-xs text-text-muted border-b border-border pb-1">Min. value</span>
        {CARD_METRICS.map(({ key, label }) => {
          const unit = key === 'winRateDifference' ? 'pp' : '%'
          return (
            <Fragment key={key}>
              <label htmlFor={`minimum-games-${key}`} className="text-sm">{LABELS[key]}</label>
              <input
                id={`minimum-games-${key}`}
                aria-label={`Minimum ${label.toLowerCase()} games`}
                type="number" min="0" step="1" inputMode="numeric" placeholder="0"
                value={minimums[key]}
                onChange={(e) => setMinimum(key, e.target.value)}
                className={INPUT}
              />
              <div className="relative">
                <input
                  aria-label={`Minimum ${label.toLowerCase()} value (${unit})`}
                  type="number" min={key === 'winRateDifference' ? -100 : 0} max="100" step="any" placeholder="Any"
                  value={minimumValues[key]}
                  onChange={(e) => onMinimumValues({ ...minimumValues, [key]: e.target.value })}
                  className={`${INPUT} pr-8`}
                />
                <span aria-hidden="true" className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-text-muted">{unit}</span>
              </div>
            </Fragment>
          )
        })}
      </div>
      <p className="text-xs text-text-muted mt-3">
        All limits apply together. Blank means no limit. Samples count player-games, one per player per game.
      </p>
    </div>
  )
}
