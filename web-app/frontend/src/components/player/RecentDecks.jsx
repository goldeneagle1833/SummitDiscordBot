import CollapsibleSection from './CollapsibleSection'

export default function RecentDecks({ decks, open, onToggle }) {
  if (!decks?.length) return null

  return (
    <CollapsibleSection title="Recent Decks" open={open} onToggle={onToggle}>
      <div className="space-y-2">
        {decks.map((deck) => (
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
            <a
              href={deck.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-secondary hover:underline whitespace-nowrap"
            >
              View Deck &rarr;
            </a>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  )
}
