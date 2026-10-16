import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import ShopifyApparel, { BUY_BUTTON_OPTIONS } from '../ShopifyApparel'

describe('ShopifyApparel', () => {
  afterEach(() => { delete window.ShopifyBuy })

  it('draws the one Shopify shirt listing in our styling with its own checkout', async () => {
    const createComponent = vi.fn()
    const buildClient = vi.fn(() => 'client')
    window.ShopifyBuy = { buildClient, UI: { onReady: vi.fn(() => Promise.resolve({ createComponent })) } }

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
})
