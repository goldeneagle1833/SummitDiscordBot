export default function DeckViewer({ deck }) {
  if (!deck) return null

  const grouped = {}
  for (const card of deck.cards || []) {
    const type = card.type || 'Other'
    if (!grouped[type]) grouped[type] = []
    grouped[type].push(card)
  }

  return (
    <div className="space-y-6">
      {/* Avatar Header */}
      {deck.avatar && (
        <div className="flex items-center gap-4 p-4 bg-bg-surface rounded-soft border border-border">
          {deck.avatar.image_url && (
            <img src={deck.avatar.image_url} alt={deck.avatar.name} className="h-16 w-16 rounded object-cover" />
          )}
          <div>
            <h3 className="text-lg font-semibold">{deck.avatar.name}</h3>
            {deck.avatar.element && <p className="text-sm text-text-muted capitalize">{deck.avatar.element}</p>}
          </div>
        </div>
      )}

      {/* Card Groups */}
      {Object.entries(grouped).map(([type, cards]) => (
        <div key={type}>
          <h4 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">
            {type} ({cards.reduce((sum, c) => sum + (c.quantity || 1), 0)})
          </h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {cards.map((card, i) => (
              <div key={`${card.name}-${i}`} className="bg-bg-surface border border-border rounded-soft p-2 text-center">
                {card.image_url && (
                  <img src={card.image_url} alt={card.name} className="w-full rounded mb-1" loading="lazy" />
                )}
                <p className="text-xs font-medium truncate">{card.name}</p>
                {card.quantity > 1 && <p className="text-xs text-text-muted">x{card.quantity}</p>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
