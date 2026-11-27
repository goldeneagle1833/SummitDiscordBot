import { describe, it, expect } from 'vitest'
import { applyPromoLayout, orderBySlots } from '../promoSlides'

const s = (...slots) => slots.map(slot => ({ slot }))
const slots = (items) => items.map(i => i.slot)

describe('promo carousel layout', () => {
  it('keeps the default order with no saved layout', () => {
    expect(slots(applyPromoLayout(s('kudos', 'promo-1', 'staff-pick'), null))).toEqual(['kudos', 'promo-1', 'staff-pick'])
    expect(slots(applyPromoLayout(s('kudos', 'promo-1'), { order: [], hidden: [] }))).toEqual(['kudos', 'promo-1'])
  })

  it('follows the saved order and drops hidden slots', () => {
    const out = applyPromoLayout(s('kudos', 'new-event', 'promo-1', 'staff-pick'), {
      order: ['staff-pick', 'promo-1', 'kudos', 'new-event'], hidden: ['kudos'],
    })
    expect(slots(out)).toEqual(['staff-pick', 'promo-1', 'new-event'])
  })

  it('puts a slide never saved right after its default neighbour', () => {
    // promo-9 is a newly shared video; by default it follows new-event
    const out = orderBySlots(s('kudos', 'new-event', 'promo-9', 'spotlight'), ['spotlight', 'new-event', 'kudos'])
    expect(slots(out)).toEqual(['spotlight', 'new-event', 'promo-9', 'kudos'])
  })

  it('puts an unsaved first slide at the front', () => {
    expect(slots(orderBySlots(s('kudos', 'spotlight'), ['spotlight']))).toEqual(['kudos', 'spotlight'])
  })
})
