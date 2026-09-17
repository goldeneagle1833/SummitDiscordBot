import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Routes, Route } from 'react-router-dom'
import { screen, renderWithRouter, userEvent } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return {
    ...actual,
    getProducts: vi.fn(),
    getCheckoutPrefill: vi.fn(),
    createCheckout: vi.fn(),
  }
})

import { useAuth } from '@/context/AuthContext'
import { getProducts, getCheckoutPrefill, createCheckout } from '@/api/store'
import { CART_KEY, loadCart } from '@/hooks/useStoreCart'
import StoreCheckout from '../StoreCheckout'

const TOKEN = { id: 1, name: 'Fire Token', price_cents: 500, currency: 'USD', stock_quantity: 10 }
const RARE = { id: 2, name: 'Rare Token', price_cents: 1500, currency: 'USD', stock_quantity: 10 }

function renderCheckout() {
  return renderWithRouter(
    <Routes>
      <Route path="/store/checkout" element={<StoreCheckout />} />
      <Route path="/store" element={<div>store page</div>} />
      <Route path="/login" element={<div>login page</div>} />
    </Routes>,
    { route: '/store/checkout' },
  )
}

describe('StoreCheckout page', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    useAuth.mockReturnValue({ user: { id: 'buyer', auth_provider: 'discord' }, loading: false })
    getProducts.mockResolvedValue({ products: [TOKEN, RARE] })
    getCheckoutPrefill.mockResolvedValue({ email: null, free_shipping: false })
  })

  it('builds the order from the saved cart with current prices', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 2 }))
    getProducts.mockResolvedValue({ products: [{ ...TOKEN, price_cents: 600 }, RARE] })
    renderCheckout()
    expect(await screen.findByText('Fire Token')).toBeInTheDocument()
    expect(screen.queryByText('Rare Token')).not.toBeInTheDocument()
    expect(screen.getAllByText('$12.00').length).toBeGreaterThan(0)
  })

  it('survives a refresh because the cart comes from storage', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 2: 1 }))
    const first = renderCheckout()
    expect(await screen.findByText('Rare Token')).toBeInTheDocument()
    first.unmount()

    renderCheckout()
    expect(await screen.findByText('Rare Token')).toBeInTheDocument()
  })

  it('sends only product ids and quantities, and keeps the cart until payment', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 2, 2: 1 }))
    createCheckout.mockReturnValue(new Promise(() => {})) // stay on "redirecting"
    renderCheckout()
    await userEvent.click(await screen.findByRole('button', { name: /Continue to payment/ }))

    expect(createCheckout).toHaveBeenCalledWith({
      items: [
        { product_id: 1, quantity: 2 },
        { product_id: 2, quantity: 1 },
      ],
      email: undefined,
    })
    expect(screen.getByText('Redirecting to Stripe...')).toBeInTheDocument()
    expect(loadCart()).toEqual({ 1: 2, 2: 1 })
  })

  it('clamps the saved cart to current stock', async () => {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 9 }))
    getProducts.mockResolvedValue({ products: [{ ...TOKEN, stock_quantity: 3 }] })
    renderCheckout()
    expect(await screen.findByText('3x')).toBeInTheDocument()
    expect(loadCart()).toEqual({ 1: 3 })
  })

  it('sends buyers with an empty cart back to the store', async () => {
    renderCheckout()
    expect(await screen.findByText('store page')).toBeInTheDocument()
  })

  it('waits for auth instead of bouncing to login', () => {
    useAuth.mockReturnValue({ user: null, loading: true })
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 1 }))
    renderCheckout()
    expect(screen.queryByText('login page')).not.toBeInTheDocument()
    expect(getProducts).not.toHaveBeenCalled()
  })

  it('sends signed-out visitors to login with the cart intact', () => {
    useAuth.mockReturnValue({ user: false, loading: false })
    sessionStorage.setItem(CART_KEY, JSON.stringify({ 1: 1 }))
    renderCheckout()
    expect(screen.getByText('login page')).toBeInTheDocument()
    expect(loadCart()).toEqual({ 1: 1 })
  })
})
