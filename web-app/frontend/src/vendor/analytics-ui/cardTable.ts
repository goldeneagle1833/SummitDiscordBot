export interface Rate { playerGames: number | null; matches: number | null; wins: number | null; winRate: number | null }
export interface CardRow {
  cardKey: string; cardName: string; deckShare: number | null
  inDeck: Rate; played: Rate; openingHand: Rate; inDeckUnplayed: Rate
}
export interface CardMetadata { name: string; type: string; elements: readonly string[]; rarity: string; imageUrl?: string }
export type MetricKey = 'deckShare' | 'inDeck' | 'played' | 'openingHand' | 'inDeckUnplayed' | 'winRateDifference'
export type SortKey = 'cardName' | MetricKey | string
export type SortDirection = 'ascending' | 'descending'
export interface CardTableFilters {
  search: string; type: string; element: string; rarity: string
  minimums: Record<MetricKey, string>
  minimumValues?: Partial<Record<MetricKey, string>>
}

export const CARD_TABLE_LIMIT = 50
export const CARD_METRICS = [
  { key: 'deckShare', label: 'Deck share' },
  { key: 'inDeck', label: 'In deck win rate' },
  { key: 'played', label: 'Played win rate' },
  { key: 'openingHand', label: 'Opening hand win rate' },
  { key: 'inDeckUnplayed', label: 'In deck, not played' },
  { key: 'winRateDifference', label: 'Played vs. not played' },
] as const
export const EMPTY_MINIMUMS: Record<MetricKey, string> = {
  deckShare: '', inDeck: '', played: '', openingHand: '', inDeckUnplayed: '', winRateDifference: '',
}

// Summit patch: PSO adds rate columns over time (e.g. inHand / notInHand).
// Any key on a row holding a Rate object can be sorted like the built-ins.
function extraRate(card: CardRow, key: string): Rate | null {
  const value = (card as unknown as Record<string, unknown>)[key]
  return value && typeof value === 'object' && 'winRate' in value ? value as Rate : null
}

export function cardMetricValue(card: CardRow, key: MetricKey | string): number | null {
  if (key === 'deckShare') return card.deckShare
  if (key === 'winRateDifference') return card.played.winRate === null || card.inDeckUnplayed.winRate === null
    ? null : card.played.winRate - card.inDeckUnplayed.winRate
  if (key === 'inDeck' || key === 'played' || key === 'openingHand' || key === 'inDeckUnplayed') return card[key].winRate
  return extraRate(card, key)?.winRate ?? null
}

function cardMetricCount(card: CardRow, key: MetricKey | string): number | null {
  if (key === 'winRateDifference') return card.played.playerGames === null || card.inDeckUnplayed.playerGames === null
    ? null : Math.min(card.played.playerGames, card.inDeckUnplayed.playerGames)
  if (key === 'deckShare' || key === 'inDeck') return card.inDeck.playerGames
  if (key === 'played' || key === 'openingHand' || key === 'inDeckUnplayed') return card[key].playerGames
  return extraRate(card, key)?.playerGames ?? null
}

export function minimumSample(value: string): number {
  const number = Number(value)
  return Number.isSafeInteger(number) && number > 0 ? number : 0
}

/** Inputs use percentages (or percentage points for the difference), not fractions. */
export function minimumMetricValue(value: string | undefined): number | null {
  if (!value?.trim()) return null
  const number = Number(value)
  return Number.isFinite(number) ? number / 100 : null
}

function cardKey(value: string): string {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

export function indexCardMetadata(cards: readonly CardMetadata[]): Map<string, CardMetadata> {
  const result = new Map<string, CardMetadata>()
  for (const card of cards) if (!result.has(cardKey(card.name))) result.set(cardKey(card.name), card)
  return result
}

export function selectCardTable(
  cards: readonly CardRow[], catalog: ReadonlyMap<string, CardMetadata>, filters: CardTableFilters,
  sortKey: SortKey, direction: SortDirection, requestedPage = 1,
): { cards: CardRow[]; total: number; page: number; pageCount: number; start: number; end: number } {
  const search = cardKey(filters.search)
  const minimums = CARD_METRICS.map(({ key }) => ({
    key, count: minimumSample(filters.minimums[key]), value: minimumMetricValue(filters.minimumValues?.[key]),
  }))
  const matched = cards.filter((card) => {
    if (search && !cardKey(card.cardName).includes(search)) return false
    if (minimums.some(({ key, count }) => count > 0
      && (cardMetricCount(card, key) ?? 0) < count)) return false
    if (minimums.some(({ key, value }) => {
      if (value === null) return false
      const actual = cardMetricValue(card, key)
      // Keep inclusive decimal thresholds stable after subtracting two rates.
      return actual === null || actual + 1e-12 < value
    })) return false
    const definition = catalog.get(card.cardKey) ?? catalog.get(cardKey(card.cardName))
    if (filters.type && definition?.type !== filters.type) return false
    if (filters.rarity && definition?.rarity !== filters.rarity) return false
    if (filters.element) {
      if (!definition) return false
      const elements = new Set(definition.elements.map((element) => element.toLowerCase()).filter((element) => element !== 'none'))
      if (filters.element === 'None' ? elements.size !== 0
        : filters.element === 'Multi' ? elements.size < 2 : !elements.has(filters.element.toLowerCase())) return false
    }
    return true
  })
  matched.sort((left, right) => {
    if (sortKey === 'cardName') return direction === 'ascending'
      ? left.cardName.localeCompare(right.cardName) : right.cardName.localeCompare(left.cardName)
    const a = cardMetricValue(left, sortKey)
    const b = cardMetricValue(right, sortKey)
    // Suppressed or unavailable rates stay last in either direction.
    if (a === null && b !== null) return 1
    if (a !== null && b === null) return -1
    if (a !== null && b !== null && a !== b) return direction === 'ascending' ? a - b : b - a
    return (right.inDeck.playerGames ?? 0) - (left.inDeck.playerGames ?? 0)
      || left.cardName.localeCompare(right.cardName)
  })
  const pageCount = Math.max(1, Math.ceil(matched.length / CARD_TABLE_LIMIT))
  const page = Math.min(pageCount, Math.max(1, Number.isSafeInteger(requestedPage) ? requestedPage : 1))
  const offset = (page - 1) * CARD_TABLE_LIMIT
  return { cards: matched.slice(offset, offset + CARD_TABLE_LIMIT), total: matched.length, page, pageCount,
    start: matched.length ? offset + 1 : 0, end: Math.min(offset + CARD_TABLE_LIMIT, matched.length) }
}
