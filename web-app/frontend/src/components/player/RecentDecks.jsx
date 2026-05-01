import CollapsibleSection from './CollapsibleSection'

export default function RecentDecks({ decks, playerId, open, onToggle }) {
  if (!decks?.length) return null

  return (
    <CollapsibleSection title="Recent Decks" open={open} onToggle={onToggle}>
      <div className="space-y-2">
        {decks.map((deck) => {
          const encodedUrl = encodeURIComponent(deck.url)
          const statsHref = `/deck-stats/${playerId}?url=${encodedUrl}`
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
