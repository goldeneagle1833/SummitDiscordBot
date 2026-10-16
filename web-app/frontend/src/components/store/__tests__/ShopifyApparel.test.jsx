import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ShopifyApparel, { BUY_BUTTON_OPTIONS, cartSummary } from '../ShopifyApparel'

describe('ShopifyApparel', () => {
  afterEach(() => { delete window.ShopifyBuy })

  it('draws the one Shopify shirt listing in our styling with its own checkout', async () => {
    const createComponent = vi.fn(() => Promise.resolve())
    const buildClient = vi.fn(() => 'client')
    window.ShopifyBuy = { buildClient, UI: { onReady: vi.fn(() => Promise.resolve({ createComponent, closeCart: vi.fn() })) } }

    render(<ShopifyApparel />)
    expect(screen.getByRole('heading', { name: 'Apparel' })).toBeInTheDocument()
    expect(screen.getByText(/separate from\s+the other store tabs/)).toBeInTheDocument()
    await waitFor(() => expect(createComponent).toHaveBeenCalled())
    expect(buildClient).toHaveBeenCalledWith({ domain: '3d97a8-fb.myshopify.com', storefrontAccessToken: '787e2ef44b98115a0a846c1b274faeee' })
    const [type, config] = createComponent.mock.calls[0]
    expect(type).toBe('product')
    expect(config.id).toBe('9685424210159')
    expect(config.node).toBe(screen.getByTestId('shopify-apparel'))
  })

  it('keeps the jersey name note in the Shopify cart', () => {
    expect(BUY_BUTTON_OPTIONS.cart.contents.note).toBe(true)
    expect(BUY_BUTTON_OPTIONS.cart.text.noteDescription).toBe('Jersey name &/or username (if applicable)')
    expect(BUY_BUTTON_OPTIONS.cart.text.total).toBe('Subtotal')
  })

  it('keeps the quantity box dark, even beside the Add to cart button', () => {
    const { quantityInput, buttonWithQuantity } = BUY_BUTTON_OPTIONS.product.styles
    expect(quantityInput.background).toBe('#21262d')
    expect(buttonWithQuantity.quantityInput).toBe(quantityInput)
  })

  it('shows our own cart bar instead of Shopify\'s floating tab and opens Shopify\'s cart from it', async () => {
    const openCart = vi.fn()
    const cart = { model: { lineItems: [{ quantity: 2 }, { quantity: 1 }], lineItemsSubtotalPrice: { amount: '120.0' } } }
    const createComponent = vi.fn((type, config) => {
      config.options.cart.events.afterRender(cart)
      return Promise.resolve()
    })
    window.ShopifyBuy = { buildClient: vi.fn(), UI: { onReady: vi.fn(() => Promise.resolve({ createComponent, openCart, closeCart: vi.fn() })) } }

    render(<ShopifyApparel />)
    expect(await screen.findByText('3 items')).toBeInTheDocument()
    expect(screen.getByText('$120.00')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /View cart/ }))
    expect(openCart).toHaveBeenCalled()
  })

  it('has no cart bar while the apparel cart is empty', () => {
    expect(cartSummary({ model: { lineItems: [] } })).toEqual({ count: 0, subtotalCents: 0 })
    expect(cartSummary(undefined)).toEqual({ count: 0, subtotalCents: 0 })
  })
})
