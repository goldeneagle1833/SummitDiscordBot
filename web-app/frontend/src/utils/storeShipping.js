// Shipping per store listing. Mirrors services/store_shipping.py: cards add
// up across the cart (up to envelope_max_cards in a plain white envelope,
// more by USPS Ground Advantage), a listing's own shipping price wins when
// it's higher, and a listing with neither set leaves shipping to payment.

export const DEFAULT_SHIPPING_RULES = {
  envelope_max_cards: 6,
  envelope_cents: 199,
  ground_cents: 599,
}

const isSet = (v) => v !== null && v !== undefined && v !== ''

export function cardsShipping(cards, rules = DEFAULT_SHIPPING_RULES) {
  if (cards <= 0) return { cents: 0, method: 'none' }
  return cards <= rules.envelope_max_cards
    ? { cents: rules.envelope_cents, method: 'envelope' }
    : { cents: rules.ground_cents, method: 'ground' }
}

// lines: [{ product, quantity }] -> { cents, cards, method } or null
export function cartShipping(lines, rules = DEFAULT_SHIPPING_RULES) {
  if (!lines.length) return null
  let cards = 0
  let own = 0
  for (const { product, quantity } of lines) {
    const perCard = product.ship_cards
    const price = product.shipping_cents
    if (!isSet(perCard) && !isSet(price)) return null
    if (isSet(perCard)) cards += Number(perCard) * Number(quantity)
    if (isSet(price)) own = Math.max(own, Number(price))
  }
  const byCards = cardsShipping(cards, rules)
  if (own > byCards.cents) return { cents: own, cards, method: 'listing' }
  return { ...byCards, cards }
}

export function shippingLabel(result, rules = DEFAULT_SHIPPING_RULES) {
  if (!result) return ''
  if (result.method === 'envelope') {
    return `Plain white envelope (up to ${rules.envelope_max_cards} cards)`
  }
  if (result.method === 'ground') return 'USPS Ground Advantage'
  if (result.method === 'none') return 'Nothing to ship'
  return 'Shipping'
}
