import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, cancelMyOrder: vi.fn() }
})

import { useAuth } from '@/context/AuthContext'
import { cancelMyOrder } from '@/api/store'
import { ApiError } from '@/api/client'
import { CART_KEY, loadCart } from '@/hooks/useStoreCart'
import StoreCancelled from '../StoreCancelled'

const ROUTE = '/store/cancelled?order=SUM-20260916-ABC123'

describe('StoreCancelled page', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    useAuth.mockReturnValue({ user: { id: 'buyer' }, loading: false })
  })

  it('cancels the pending order and keeps the cart', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 2 }))
    cancelMyOrder.mockResolvedValue({ success: true, status: 'cancelled' })
    renderWithRouter(<StoreCancelled />, { route: ROUTE })

    expect(await screen.findByText(/Your items have been released/)).toBeInTheDocument()
    expect(cancelMyOrder).toHaveBeenCalledWith('SUM-20260916-ABC123')
    expect(loadCart()).toEqual({ 1: 2 })
  })

  it('says so when the payment went through after all', async () => {
    cancelMyOrder.mockRejectedValue(new ApiError(409, 'This order has already been paid'))
    renderWithRouter(<StoreCancelled />, { route: ROUTE })

    expect(await screen.findByText('Your payment went through')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View my orders' })).toHaveAttribute('href', '/store/orders')
  })

  it('falls back to the automatic release message on other errors', async () => {
    cancelMyOrder.mockRejectedValue(new ApiError(502, 'Could not cancel'))
    renderWithRouter(<StoreCancelled />, { route: ROUTE })
    expect(await screen.findByText(/released automatically within an hour/)).toBeInTheDocument()
  })

  it('waits for auth before cancelling', () => {
    useAuth.mockReturnValue({ user: null, loading: true })
    renderWithRouter(<StoreCancelled />, { route: ROUTE })
    expect(cancelMyOrder).not.toHaveBeenCalled()
    expect(screen.getByText(/Releasing your items/)).toBeInTheDocument()
  })

  it('does not try to cancel when signed out', async () => {
    useAuth.mockReturnValue({ user: false, loading: false })
    renderWithRouter(<StoreCancelled />, { route: ROUTE })
    expect(await screen.findByText(/released automatically within an hour/)).toBeInTheDocument()
    expect(cancelMyOrder).not.toHaveBeenCalled()
  })

  it('does nothing without an order number', () => {
    renderWithRouter(<StoreCancelled />, { route: '/store/cancelled' })
    expect(cancelMyOrder).not.toHaveBeenCalled()
    expect(screen.getByText('Checkout cancelled')).toBeInTheDocument()
  })
})
