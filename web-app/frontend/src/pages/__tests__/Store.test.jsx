import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Routes, Route } from 'react-router-dom'
import { screen, renderWithRouter, userEvent, waitFor } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, getProducts: vi.fn() }
})

import { useAuth } from '@/context/AuthContext'
import { getProducts } from '@/api/store'
import { CART_KEY, loadCart } from '@/hooks/useStoreCart'
import Store from '../Store'

const TOKEN = { id: 1, name: 'Fire Token', price_cents: 500, currency: 'USD', stock_quantity: 10, max_per_user_monthly: null }
const CAPPED = { id: 2, name: 'Rare Token', price_cents: 1500, currency: 'USD', stock_quantity: 10, max_per_user_monthly: 3 }

function renderStore() {
  return renderWithRouter(
    <Routes>
      <Route path="/store" element={<Store />} />
      <Route path="/store/checkout" element={<div>checkout page</div>} />
    </Routes>,
    { route: '/store' },
  )
}

describe('Store page', () => {
  beforeEach(() => {
    sessionStorage.clear()
    getProducts.mockReset()
    useAuth.mockReturnValue({ user: false, loading: false })
  })

  it('does not pop the sign-in prompt when a guest arrives', async () => {
    getProducts.mockResolvedValue({ products: [TOKEN] })
    renderStore()
    expect(await screen.findByText('Fire Token')).toBeInTheDocument()
    expect(screen.queryByText('Sign in to check out')).not.toBeInTheDocument()
  })

  it('shows the sign-in prompt when a guest tries to check out', async () => {
    getProducts.mockResolvedValue({ products: [TOKEN] })
    renderStore()
    await userEvent.click(await screen.findByLabelText('Add one Fire Token'))
    await userEvent.click(screen.getByRole('button', { name: 'Log in to check out' }))
    expect(screen.getByText('Sign in to check out')).toBeInTheDocument()
    expect(screen.getByText(/Your cart is saved/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Keep browsing' }))
    expect(screen.queryByText('Sign in to check out')).not.toBeInTheDocument()
  })

  it('saves the cart as items are added', async () => {
    getProducts.mockResolvedValue({ products: [TOKEN] })
    renderStore()
    const add = await screen.findByLabelText('Add one Fire Token')
    await userEvent.click(add)
    await userEvent.click(add)
    expect(loadCart()).toEqual({ 1: 2 })
  })

  it('restores a saved cart (e.g. after signing in)', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 2 }))
    getProducts.mockResolvedValue({ products: [TOKEN] })
    renderStore()
    expect(await screen.findByText('2 items')).toBeInTheDocument()
    expect(screen.getByText('$10.00')).toBeInTheDocument()
  })

  it('drops sold-out items and clamps quantities in a saved cart', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 5, 2: 3 }))
    getProducts.mockResolvedValue({
      products: [
        { ...TOKEN, stock_quantity: 2 },
        { ...CAPPED, stock_quantity: 0 },
      ],
    })
    renderStore()
    expect(await screen.findByText('2 items')).toBeInTheDocument()
    await waitFor(() => expect(loadCart()).toEqual({ 1: 2 }))
  })

  it('caps the quantity at the buyer’s remaining monthly allowance', async () => {
    useAuth.mockReturnValue({ user: { id: 'buyer' }, loading: false })
    getProducts.mockResolvedValue({ products: [{ ...CAPPED, remaining_this_month: 1 }] })
    renderStore()
    expect(await screen.findByText(/Limit 3 per month/)).toHaveTextContent('1 left for you')
    const add = screen.getByLabelText('Add one Rare Token')
    await userEvent.click(add)
    expect(add).toBeDisabled()
  })

  it('shows the limit without a remaining count for guests', async () => {
    getProducts.mockResolvedValue({ products: [CAPPED] })
    renderStore()
    const note = await screen.findByText(/Limit 3 per month/)
    expect(note).not.toHaveTextContent('left for you')
  })

  it('replaces the quantity picker once the monthly limit is used up', async () => {
    useAuth.mockReturnValue({ user: { id: 'buyer' }, loading: false })
    getProducts.mockResolvedValue({ products: [{ ...CAPPED, remaining_this_month: 0 }] })
    renderStore()
    expect(await screen.findByText('Monthly limit reached')).toBeInTheDocument()
    expect(screen.queryByLabelText('Add one Rare Token')).not.toBeInTheDocument()
  })

  it('goes to checkout for a signed-in buyer', async () => {
    useAuth.mockReturnValue({ user: { id: 'buyer' }, loading: false })
    getProducts.mockResolvedValue({ products: [TOKEN] })
    renderStore()
    await userEvent.click(await screen.findByLabelText('Add one Fire Token'))
    await userEvent.click(screen.getByRole('button', { name: /Checkout/ }))
    expect(screen.getByText('checkout page')).toBeInTheDocument()
  })
})
