import { describe, it, expect, beforeEach } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import { CART_KEY, loadCart } from '@/hooks/useStoreCart'
import StoreSuccess from '../StoreSuccess'

describe('StoreSuccess page', () => {
  beforeEach(() => sessionStorage.clear())

  it('clears the cart once the order is paid', () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 2 }))
    renderWithRouter(<StoreSuccess />, { route: '/store/success?order=SUM-20260916-ABC123' })
    expect(screen.getByText('SUM-20260916-ABC123')).toBeInTheDocument()
    expect(loadCart()).toEqual({})
  })
})
