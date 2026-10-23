import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Routes, Route } from 'react-router-dom'
import { screen, renderWithRouter, userEvent, waitFor, within } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, getProducts: vi.fn(), getStorefronts: vi.fn() }
})

import { useAuth } from '@/context/AuthContext'
import { getProducts, getStorefronts } from '@/api/store'
import { CART_KEY, loadCart, cartKey } from '@/hooks/useStoreCart'
import Store from '../Store'

const TOKEN = { id: 1, name: 'Fire Token', price_cents: 500, currency: 'USD', stock_quantity: 10, max_per_user_monthly: null }
const CAPPED = { id: 2, name: 'Rare Token', price_cents: 1500, currency: 'USD', stock_quantity: 10, max_per_user_monthly: 3 }

function CheckoutStub() {
  return <div>checkout page{window.location.search}</div>
}

function renderStore(route = '/store') {
  return renderWithRouter(
    <Routes>
      <Route path="/store" element={<Store />} />
      <Route path="/store/checkout" element={<CheckoutStub />} />
    </Routes>,
    { route },
  )
}

describe('Store page', () => {
  beforeEach(() => {
    sessionStorage.clear()
    getProducts.mockReset()
    getStorefronts.mockReset()
    getStorefronts.mockResolvedValue({ storefronts: [] })
    useAuth.mockReturnValue({ user: false, loading: false })
  })

  it('shows a thumbnail strip for products with several images and switches the main image', async () => {
    getProducts.mockResolvedValue({
      products: [{ ...TOKEN, images: ['/one.png', '/two.png', '/three.png'] }],
    })
    renderStore()
    const main = await screen.findByAltText('Fire Token')
    expect(main).toHaveAttribute('src', '/one.png')

    await userEvent.click(screen.getByLabelText('Show image 2 of Fire Token'))
    expect(screen.getByAltText('Fire Token')).toHaveAttribute('src', '/two.png')
  })

  it('opens the clicked image full screen and steps through the others', async () => {
    getProducts.mockResolvedValue({
      products: [{ ...TOKEN, images: ['/one.png', '/two.png', '/three.png'] }],
    })
    renderStore()
    await userEvent.click(await screen.findByLabelText('Show image 2 of Fire Token'))
    await userEvent.click(screen.getByLabelText('View Fire Token image full screen'))

    const viewer = screen.getByRole('dialog', { name: 'Fire Token image viewer' })
    expect(within(viewer).getByAltText('Fire Token')).toHaveAttribute('src', '/two.png')
    expect(viewer).toHaveTextContent('2 / 3')

    await userEvent.click(within(viewer).getByLabelText('Next image'))
    expect(within(viewer).getByAltText('Fire Token')).toHaveAttribute('src', '/three.png')
    await userEvent.keyboard('{ArrowRight}')
    expect(within(viewer).getByAltText('Fire Token')).toHaveAttribute('src', '/one.png')
    await userEvent.click(within(viewer).getByLabelText('Previous image'))
    expect(within(viewer).getByAltText('Fire Token')).toHaveAttribute('src', '/three.png')

    // Clicking the image itself keeps the viewer open
    await userEvent.click(within(viewer).getByAltText('Fire Token'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes the full screen image with the X or a click outside it', async () => {
    getProducts.mockResolvedValue({ products: [{ ...TOKEN, image_url: '/solo.png', images: ['/solo.png'] }] })
    renderStore()
    await userEvent.click(await screen.findByLabelText('View Fire Token image full screen'))
    expect(screen.queryByLabelText('Next image')).not.toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Close image viewer'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('View Fire Token image full screen'))
    await userEvent.click(screen.getByRole('dialog'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows a single image without a thumbnail strip', async () => {
    getProducts.mockResolvedValue({ products: [{ ...TOKEN, image_url: '/solo.png', images: ['/solo.png'] }] })
    renderStore()
    expect(await screen.findByAltText('Fire Token')).toHaveAttribute('src', '/solo.png')
    expect(screen.queryByLabelText('Fire Token images')).not.toBeInTheDocument()
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

describe('Store storefront tabs', () => {
  const SUMMIT = { id: 1, slug: 'summit', name: 'Summit Store', description: '' }
  const EXPLORER = { id: 2, slug: 'explorer', name: 'Explorer Store', description: 'Explorer series gear' }
  const MAT = { id: 9, name: 'Explorer Mat', price_cents: 2000, currency: 'USD', stock_quantity: 5, max_per_user_monthly: null, storefront_id: 2 }

  beforeEach(() => {
    sessionStorage.clear()
    getProducts.mockReset()
    getStorefronts.mockReset()
    useAuth.mockReturnValue({ user: { id: 'buyer' }, loading: false })
    getStorefronts.mockResolvedValue({ storefronts: [SUMMIT, EXPLORER] })
    getProducts.mockResolvedValue({ products: [{ ...TOKEN, storefront_id: 1 }, MAT] })
  })

  it('titles the page and no longer offers storefront applications', async () => {
    renderStore()
    expect(await screen.findByRole('heading', { name: 'Sorcery Community Store' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Apply to have a storefront' })).not.toBeInTheDocument()
  })

  it('shows one storefront at a time', async () => {
    renderStore()
    expect(await screen.findByText('Fire Token')).toBeInTheDocument()
    expect(screen.queryByText('Explorer Mat')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /Explorer Store/ }))
    expect(screen.getByText('Explorer Mat')).toBeInTheDocument()
    expect(screen.getByText('Explorer series gear')).toBeInTheDocument()
    expect(screen.queryByText('Fire Token')).not.toBeInTheDocument()
  })

  it("won't check out a storefront that isn't taking orders yet", async () => {
    getStorefronts.mockResolvedValue({ storefronts: [SUMMIT, { ...EXPLORER, accepts_payments: false }] })
    renderStore('/store?storefront=explorer')
    expect(await screen.findByText(/Explorer Store isn't taking orders yet/)).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Add one Explorer Mat'))
    expect(screen.getByRole('button', { name: 'Not taking orders yet' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /^Checkout/ })).not.toBeInTheDocument()
  })

  it('has no Explorer Apparel tab, and old apparel links open the Summit Store', async () => {
    renderStore('/store?tab=explorer-apparel')
    expect(await screen.findByText('Fire Token')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Summit Store/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('tab', { name: /Apparel/ })).not.toBeInTheDocument()
  })

  it('highlights US shipping only on every storefront, with its own note', async () => {
    getStorefronts.mockResolvedValue({
      storefronts: [SUMMIT, { ...EXPLORER, shipping_note: 'LIMITED RUN PRE-ORDER' }],
    })
    renderStore()
    expect(await screen.findByText(/US shipping only/)).toBeInTheDocument()
    expect(screen.queryByText('LIMITED RUN PRE-ORDER')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: /Explorer Store/ }))
    expect(screen.getByText(/US shipping only/)).toBeInTheDocument()
    expect(screen.getByText('LIMITED RUN PRE-ORDER')).toBeInTheDocument()
  })

  it('opens the tab named in the link', async () => {
    renderStore('/store?storefront=explorer')
    expect(await screen.findByText('Explorer Mat')).toBeInTheDocument()
  })

  it('keeps a separate cart per storefront', async () => {
    renderStore()
    await userEvent.click(await screen.findByLabelText('Add one Fire Token'))
    await userEvent.click(screen.getByRole('tab', { name: /Explorer Store/ }))
    await userEvent.click(screen.getByLabelText('Add one Explorer Mat'))
    await userEvent.click(screen.getByLabelText('Add one Explorer Mat'))

    expect(loadCart('summit')).toEqual({ 1: 1 })
    expect(loadCart('explorer')).toEqual({ 9: 2 })
    expect(sessionStorage.getItem(cartKey('explorer'))).not.toBeNull()
    expect(screen.getByText('Explorer Store cart')).toBeInTheDocument()
    // The other storefront's tab shows what's waiting in its cart
    expect(screen.getByLabelText('1 in cart')).toBeInTheDocument()
  })

  it('checks out only the open storefront', async () => {
    renderStore('/store?storefront=explorer')
    await userEvent.click(await screen.findByLabelText('Add one Explorer Mat'))
    await userEvent.click(screen.getByRole('button', { name: /Checkout/ }))
    expect(screen.getByText(/checkout page/)).toBeInTheDocument()
  })
})
