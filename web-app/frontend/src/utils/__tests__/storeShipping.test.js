import { describe, it, expect } from 'vitest'
import { cartShipping, cardsShipping } from '../storeShipping'

const playset = { ship_cards: 6, shipping_cents: null }
const pack = { ship_cards: 2, shipping_cents: null }

describe('store shipping', () => {
  it('ships up to six cards in an envelope', () => {
    expect(cardsShipping(6)).toEqual({ cents: 199, method: 'envelope' })
    expect(cartShipping([{ product: playset, quantity: 1 }]).cents).toBe(199)
  })

  it('goes Ground Advantage over six cards', () => {
    const r = cartShipping([{ product: playset, quantity: 1 }, { product: pack, quantity: 1 }])
    expect(r).toEqual({ cents: 599, method: 'ground', cards: 8 })
  })

  it("uses a listing's own price when higher", () => {
    const mat = { ship_cards: null, shipping_cents: 899 }
    expect(cartShipping([{ product: mat, quantity: 1 }, { product: pack, quantity: 1 }]).cents).toBe(899)
  })

  it('leaves shipping to payment when a listing is not set', () => {
    const other = { ship_cards: null, shipping_cents: null }
    expect(cartShipping([{ product: other, quantity: 1 }, { product: pack, quantity: 1 }])).toBeNull()
  })
})
