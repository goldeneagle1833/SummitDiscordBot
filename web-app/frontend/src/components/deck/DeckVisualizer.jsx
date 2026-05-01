const CARD_TYPE_ORDER = ['Minion', 'Magic', 'Artifact', 'Aura', 'Site', 'Other']

function getCardType(card) {
  const type = (card.type || '').toLowerCase()
  if (type.includes('minion')) return 'Minion'
  if (type.includes('magic')) return 'Magic'
  if (type.includes('artifact')) return 'Artifact'
  if (type.includes('aura')) return 'Aura'
  if (type.includes('site')) return 'Site'
  return 'Other'
}

function getManaCost(card) {
  return card.threshold || card.cost || card.mana || card.mana_cost || 0
}

/**
 * Shared Deck Visualizer - displays card images in a grid, grouped by type.
 *
 * Accepts cards in two formats:
 *   1. Snapshot format: { deck: { spellbook: [], atlas: [], sideboard: [] } }
 *      Pass `spellbook`, `atlas`, `sideboard` as separate props.
 *   2. Flat card list: pass `cards` prop directly.
 *
 * Each card object should have: name, image (filename), quantity/qty, type (optional).
 */
export default function DeckVisualizer({ cards, spellbook, atlas, sideboard }) {
  // Merge all sources into one list
  let allCards = []
  if (cards) {
    allCards = cards
  } else {
    if (spellbook) allCards.push(...spellbook)
    if (atlas) allCards.push(...atlas)
    if (sideboard) allCards.push(...sideboard)
  }

  const withImages = allCards.filter((c) => c.image)

  if (!withImages.length) {
    return (
      <div className="bg-bg-surface border border-border rounded-lg p-6 text-center">
        <p className="text-text-muted text-sm">Visual deck view coming soon. Card images not available for this deck.</p>
      </div>
    )
  }

  // Group by type and sort by mana cost within each group
  const groups = {}
  CARD_TYPE_ORDER.forEach((t) => { groups[t] = [] })
  withImages.forEach((card) => {
    const type = getCardType(card)
    if (!groups[type]) groups[type] = []
    groups[type].push(card)
  })
  for (const type of Object.keys(groups)) {
    groups[type].sort((a, b) => getManaCost(a) - getManaCost(b))
  }

  return (
    <div className="space-y-4">
      {CARD_TYPE_ORDER.map((type) => {
        const cards = groups[type]
        if (!cards?.length) return null
        const heading = type === 'Site' ? 'Atlas' : type + 's'
        const totalQty = cards.reduce((sum, c) => sum + (c.quantity || c.qty || 1), 0)
        return (
          <div key={type}>
            <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              {heading} ({totalQty})
            </h4>
            <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8 gap-2">
              {cards.map((card, i) => {
                const qty = card.quantity || card.qty || 1
                return (
                  <div key={`${card.name}-${i}`} className="relative">
                    <img
                      src={`/card-images/${card.image}`}
                      alt={card.name}
                      className="w-full rounded shadow-sm"
                      loading="lazy"
                    />
                    {qty > 1 && (
                      <span className="absolute top-1 right-1 bg-black/70 text-white text-xs font-bold px-1.5 py-0.5 rounded">
                        x{qty}
                      </span>
                    )}
                    <p className="text-xs text-text-muted text-center mt-1 truncate">{card.name}</p>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
