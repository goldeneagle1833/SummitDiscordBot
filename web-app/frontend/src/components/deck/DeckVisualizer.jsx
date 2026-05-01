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

  // Each copy is offset 15% of the card's height below the previous one.
  // translateY(%) uses the element's own height, so 15% = 15% of card height directly.
  // paddingTop(%) uses the parent's width, so we multiply by the card aspect ratio (height/width ≈ 1.386).
  const GAP_PCT = 15
  const CARD_RATIO = 1.386 // Sorcery card height/width ratio (88mm / 63.5mm)
  const GAP_WIDTH_PCT = GAP_PCT * CARD_RATIO // ≈ 20.8% of width per step

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
                const stackCount = Math.min(qty, 4)
                return (
                  <div key={`${card.name}-${i}`}>
                    {/*
                      paddingTop reserves space at top so background copies
                      (which start at y=0) can peek above the front card.
                      The invisible spacer img establishes the correct height
                      for the front card at y=maxOffset.
                    */}
                    <div className="relative" style={{ paddingTop: `${((stackCount - 1) * GAP_WIDTH_PCT).toFixed(2)}%` }}>
                      {/* Invisible spacer sets container height = cardHeight at this width */}
                      <img
                        src={`/card-images/${card.image}`}
                        alt=""
                        aria-hidden="true"
                        className="w-full"
                        style={{ visibility: 'hidden' }}
                      />
                      {/*
                        All copies absolutely positioned at top:0, then shifted down.
                        j=0 → y=0 (top of stack, back/lowest z), j=N-1 → y=maxOffset (front/highest z).
                      */}
                      {Array.from({ length: stackCount }).map((_, j) => {
                        const isFront = j === stackCount - 1
                        return (
                          <div
                            key={j}
                            className="absolute top-0 left-0 w-full"
                            style={{
                              transform: `translateY(${j * GAP_PCT}%)`,
                              zIndex: j + 1,
                            }}
                          >
                            <img
                              src={`/card-images/${card.image}`}
                              alt={isFront ? card.name : ''}
                              aria-hidden={!isFront || undefined}
                              className="w-full rounded"
                              style={{ filter: 'drop-shadow(0 3px 6px rgba(0,0,0,0.55))' }}
                              loading="lazy"
                            />
                            {isFront && qty > 1 && (
                              <span
                                className="absolute bottom-1 right-1 bg-black/70 text-white text-xs font-bold px-1.5 py-0.5 rounded"
                              >
                                x{qty}
                              </span>
                            )}
                          </div>
                        )
                      })}
                    </div>
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
