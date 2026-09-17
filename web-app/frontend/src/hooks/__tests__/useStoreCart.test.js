import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useStoreCart, {
  CART_KEY, loadCart, saveCart, clearCart, maxQuantity, reconcileCart,
} from '../useStoreCart'

const product = (overrides) => ({ id: 1, stock_quantity: 10, ...overrides })

describe('store cart storage', () => {
  beforeEach(() => sessionStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('round-trips a cart through sessionStorage', () => {
    saveCart({ 1: 2, 7: 1 })
    expect(loadCart()).toEqual({ 1: 2, 7: 1 })
  })

  it('removes the key when the cart is emptied', () => {
    saveCart({ 1: 2 })
    saveCart({})
    expect(sessionStorage.getItem(CART_KEY)).toBeNull()
  })

  it('clearCart removes the saved cart', () => {
    saveCart({ 1: 2 })
    clearCart()
    expect(loadCart()).toEqual({})
  })

  it('returns an empty cart for corrupt or unexpected data', () => {
    sessionStorage.setItem(CART_KEY, '{not json')
    expect(loadCart()).toEqual({})
    sessionStorage.setItem(CART_KEY, '[1,2]')
    expect(loadCart()).toEqual({})
    sessionStorage.setItem(CART_KEY, 'null')
    expect(loadCart()).toEqual({})
  })

  it('drops invalid quantities', () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 2, 2: 0, 3: -1, 4: 1.5, 5: '3' }))
    expect(loadCart()).toEqual({ 1: 2 })
  })

  it('survives storage being unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked') })
    expect(loadCart()).toEqual({})
    expect(() => saveCart({ 1: 1 })).not.toThrow()
    expect(() => clearCart()).not.toThrow()
  })
})

describe('maxQuantity', () => {
  it('is the stock when there is no monthly limit info', () => {
    expect(maxQuantity(product({ stock_quantity: 4 }))).toBe(4)
  })

  it('is capped by the remaining monthly allowance', () => {
    expect(maxQuantity(product({ stock_quantity: 10, remaining_this_month: 2 }))).toBe(2)
    expect(maxQuantity(product({ stock_quantity: 1, remaining_this_month: 2 }))).toBe(1)
    expect(maxQuantity(product({ remaining_this_month: 0 }))).toBe(0)
  })
})

describe('reconcileCart', () => {
  it('drops products that are gone, sold out, or at their limit', () => {
    const products = [
      product({ id: 1 }),
      product({ id: 2, stock_quantity: 0 }),
      product({ id: 3, remaining_this_month: 0 }),
    ]
    expect(reconcileCart({ 1: 1, 2: 1, 3: 1, 99: 4 }, products)).toEqual({ 1: 1 })
  })

  it('clamps quantities to what can be bought', () => {
    const products = [
      product({ id: 1, stock_quantity: 2 }),
      product({ id: 2, remaining_this_month: 1 }),
    ]
    expect(reconcileCart({ 1: 5, 2: 3 }, products)).toEqual({ 1: 2, 2: 1 })
  })
})

describe('useStoreCart', () => {
  beforeEach(() => sessionStorage.clear())

  it('starts from the saved cart and persists changes', () => {
    saveCart({ 1: 1 })
    const { result } = renderHook(() => useStoreCart())
    expect(result.current[0]).toEqual({ 1: 1 })

    act(() => result.current[1]({ 1: 3 }))
    expect(loadCart()).toEqual({ 1: 3 })
  })
})
