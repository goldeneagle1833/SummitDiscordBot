import CollapsibleSection from './CollapsibleSection'

function signed(n) {
  return n > 0 ? `+${n}` : `${n}`
}

function EloDelta({ value }) {
  const tone = value > 0 ? 'text-accent-green' : value < 0 ? 'text-accent-red' : 'text-text-muted'
  return <span className={`font-medium ${tone}`}>{signed(value)}</span>
}

export default function RecentDecks({ decks, playerId, open, onToggle }) {
  if (!decks?.length) return null

  return (
    <CollapsibleSection title="Recent Decks" open={open} onToggle={onToggle}>
      <div className="space-y-2">
        {decks.map((deck) => {
          const encodedUrl = encodeURIComponent(deck.url)
          const statsHref = `/deck-stats/${playerId}?url=${encodedUrl}`
          const hasSeason = deck.elo_season !== null && deck.elo_season !== undefined
          const hasLifetime = deck.elo_lifetime !== null && deck.elo_lifetime !== undefined
          return (
            <div key={deck.url} className="bg-bg-raised border border-border rounded-lg p-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-text-primary truncate">{deck.deck_name}</p>
                <p className="text-xs text-text-muted">
                  {deck.avatar} &middot;{' '}
                  <span className="text-accent-green">{deck.wins}W</span>
                  {' / '}
                  <span className="text-accent-red">{deck.losses}L</span>
                  {' '}({deck.win_rate}%)
                </p>
                {(hasSeason || hasLifetime) && (
                  <p
                    className="text-xs text-text-muted mt-0.5"
                    title="Lifetime ELO gained or lost while piloting this deck"
                  >
                    ELO:{' '}
                    {hasSeason && (
                      <>
                        Season <EloDelta value={deck.elo_season} />
                        {' '}({deck.season_wins}-{deck.season_losses})
                      </>
                    )}
                    {hasSeason && hasLifetime && ' · '}
                    {hasLifetime && (
                      <>
                        Lifetime <EloDelta value={deck.elo_lifetime} />
                      </>
                    )}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <a
                  href={statsHref}
                  className="text-xs text-secondary hover:underline whitespace-nowrap"
                >
                  Stats &rarr;
                </a>
              </div>
            </div>
          )
        })}
      </div>
    </CollapsibleSection>
  )
}
