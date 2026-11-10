import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Routes, Route } from 'react-router-dom'
import { screen, renderWithRouter, userEvent, waitFor } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return {
    ...actual,
    getPrivateProduct: vi.fn(),
    getProducts: vi.fn(),
    getCheckoutPrefill: vi.fn(),
    createCheckout: vi.fn(),
  }
})

import { useAuth } from '@/context/AuthContext'
import { getPrivateProduct, getProducts, getCheckoutPrefill, createCheckout } from '@/api/store'
import { CART_KEY, loadCart } from '@/hooks/useStoreCart'
import { ApiError } from '@/api/client'
import StorePrivateProduct from '../StorePrivateProduct'
import StoreCheckout from '../StoreCheckout'

const PACK = {
  id: 5, name: 'Event Pack', description: 'Only at the event', price_cents: 1000, currency: 'USD',
  stock_quantity: 20, images: [], ship_cards: 2, shipping_cents: null,
}
const DATA = {
  product: PACK,
  storefront: { id: 1, slug: 'summit', name: 'Summit Store', accepts_payments: true },
  shipping_rules: { envelope_max_cards: 6, envelope_cents: 199, ground_cents: 599 },
}

function renderAt(route) {
  return renderWithRouter(
    <Routes>
      <Route path="/store/p/:token" element={<StorePrivateProduct />} />
      <Route path="/store/checkout" element={<StoreCheckout />} />
      <Route path="/store" element={<div>store page</div>} />
    </Routes>,
    { route },
  )
}

describe('Private listing page', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    useAuth.mockReturnValue({ user: { id: 'buyer', auth_provider: 'discord' }, loading: false })
    getPrivateProduct.mockResolvedValue(DATA)
    getCheckoutPrefill.mockResolvedValue({ email: null, free_shipping: false })
    createCheckout.mockResolvedValue({ checkout_url: 'https://stripe.example/pay' })
  })

  it('shows the listing from its link', async () => {
    renderAt('/store/p/tok123')
    expect(await screen.findByRole('heading', { name: 'Event Pack' })).toBeInTheDocument()
    expect(getPrivateProduct).toHaveBeenCalledWith('tok123')
    expect(screen.getByText('Only at the event')).toBeInTheDocument()
    expect(screen.getByText(/US shipping only/)).toBeInTheDocument()
  })

  it('says so when the link is old', async () => {
    getPrivateProduct.mockRejectedValue(new ApiError(404, 'Listing not found'))
    renderAt('/store/p/old')
    expect(await screen.findByText("This listing isn't available")).toBeInTheDocument()
  })

  it('checks out on its own with the link token, leaving the cart alone', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 2 }))
    const assign = vi.fn()
    Object.defineProperty(window, 'location', { value: { ...window.location, assign }, writable: true })
    renderAt('/store/p/tok123')
    await screen.findByRole('heading', { name: 'Event Pack' })
    await userEvent.click(screen.getByRole('button', { name: 'One more' }))
    await userEvent.click(screen.getByRole('button', { name: /Buy now/ }))
    expect(await screen.findByText('Review your order')).toBeInTheDocument()
    expect(screen.getByText('2x')).toBeInTheDocument()
    expect(getProducts).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /Continue to payment/ }))
    await waitFor(() => expect(createCheckout).toHaveBeenCalledWith({
      items: [{ product_id: 5, quantity: 2, private_token: 'tok123' }],
      email: undefined,
    }))
    expect(loadCart('summit')).toEqual({ 1: 2 })
  })

  it('asks a logged-out visitor to sign in', async () => {
    useAuth.mockReturnValue({ user: null, loading: false })
    renderAt('/store/p/tok123')
    await userEvent.click(await screen.findByRole('button', { name: 'Log in to buy' }))
    expect(screen.getByText('Sign in to check out')).toBeInTheDocument()
  })
})
