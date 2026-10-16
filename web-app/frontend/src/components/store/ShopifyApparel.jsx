import { useEffect, useRef, useState } from 'react'
import { formatMoney } from '@/api/store'

/**
 * Explorer Series apparel, sold through the Explorer team's Shopify store.
 *
 * Shopify's Buy Button draws the products and runs its own cart and
 * checkout: orders and payment go to Shopify, never through our store,
 * Store Admin or Stripe. Only the look is ours: the colors and fonts below
 * are passed to the Buy Button so it matches the site.
 */
const SDK_URL = 'https://sdks.shopifycdn.com/buy-button/latest/buy-button-storefront.min.js'
const SHOP = {
  domain: '3d97a8-fb.myshopify.com',
  // Shopify's public, read-only Storefront key, made to be embedded in pages
  storefrontAccessToken: '787e2ef44b98115a0a846c1b274faeee',
}
// Explorer Series TShirt 1 (the collection's other listing is a duplicate)
export const PRODUCT_ID = '9685424210159'

const C = {
  text: '#f0f6fc',
  muted: '#8b949e',
  gold: '#ffd700',
  surface: '#161b22',
  elevated: '#21262d',
  line: '#30363d',
  brand: '#3653a0',
  brandLight: '#4a68b8',
}
const FONT = 'Figtree, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'

const button = {
  'font-family': FONT,
  'font-weight': '600',
  'font-size': '15px',
  'padding-top': '12px',
  'padding-bottom': '12px',
  'background-color': C.brand,
  ':hover': { 'background-color': C.brandLight },
  ':focus': { 'background-color': C.brandLight },
  'border-radius': '8px',
}
const quantityInput = {
  'font-size': '15px',
  'font-family': FONT,
  'font-weight': '600',
  'padding-top': '12px',
  'padding-bottom': '12px',
  color: C.text,
  background: C.elevated,
  'border-color': C.line,
}
const lineItemText = { color: C.text }

export const BUY_BUTTON_OPTIONS = {
  product: {
    styles: {
      product: {
        '@media (min-width: 601px)': {
          'max-width': '100%',
          'margin-left': '0',
          'margin-bottom': '40px',
        },
        'text-align': 'left',
      },
      title: { 'font-family': FONT, 'font-size': '22px', 'font-weight': '600', color: C.text },
      price: { 'font-family': FONT, 'font-size': '16px', 'font-weight': '600', color: C.gold },
      compareAt: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      unitPrice: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      description: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      button,
      quantityInput,
      // Shopify's own sheet paints the box beside the button white with a
      // more specific selector; nesting matches it so ours wins
      buttonWithQuantity: { quantityInput },
    },
    buttonDestination: 'cart',
    layout: 'horizontal',
    width: '100%',
    contents: { img: false, imgWithCarousel: true, button: false, buttonWithQuantity: true, description: true },
    text: { button: 'Add to cart' },
    googleFonts: ['Figtree'],
  },
  modalProduct: {
    contents: { img: false, imgWithCarousel: true, button: false, buttonWithQuantity: true },
    styles: {
      product: {
        '@media (min-width: 601px)': { 'max-width': '100%', 'margin-left': '0px', 'margin-bottom': '0px' },
      },
      title: { 'font-family': FONT, 'font-weight': '700', 'font-size': '24px', color: C.text },
      price: { 'font-family': FONT, 'font-size': '18px', color: C.gold },
      compareAt: { 'font-family': FONT, 'font-size': '15px', color: C.muted },
      unitPrice: { 'font-family': FONT, 'font-size': '15px', color: C.muted },
      description: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      button,
      quantityInput,
      buttonWithQuantity: { quantityInput },
    },
    text: { button: 'Add to cart' },
    googleFonts: ['Figtree'],
  },
  modal: {
    styles: { modal: { 'background-color': C.surface } },
  },
  option: {
    styles: {
      label: { 'font-family': FONT, color: C.muted },
      select: { 'font-family': FONT, color: C.text, 'background-color': C.elevated, 'border-color': C.line },
    },
    googleFonts: ['Figtree'],
  },
  cart: {
    styles: {
      cart: { 'background-color': C.surface },
      footer: { 'background-color': C.surface },
      button,
      title: lineItemText,
      header: lineItemText,
      lineItems: lineItemText,
      subtotalText: lineItemText,
      subtotal: { color: C.gold },
      notice: { color: C.muted },
      currency: { color: C.muted },
      close: { color: C.muted, ':hover': { color: C.text } },
      empty: { color: C.muted },
      noteDescription: lineItemText,
      discountText: lineItemText,
      discountIcon: { fill: C.text },
      discountAmount: lineItemText,
    },
    text: {
      title: 'Apparel cart',
      total: 'Subtotal',
      notice: 'Checkout is on the Explorer Series Shopify store.',
      button: 'Checkout on Shopify',
      // Buyers type their jersey name here; it comes through as the order note
      noteDescription: 'Jersey name &/or username (if applicable)',
    },
    contents: { note: true },
    popup: false,
    googleFonts: ['Figtree'],
  },
  toggle: {
    styles: {
      toggle: {
        'font-family': FONT,
        'font-weight': '600',
        'background-color': C.brand,
        ':hover': { 'background-color': C.brandLight },
        ':focus': { 'background-color': C.brandLight },
      },
      count: { 'font-size': '15px' },
    },
    googleFonts: ['Figtree'],
  },
  lineItem: {
    styles: {
      variantTitle: { color: C.muted },
      title: lineItemText,
      price: { color: C.gold },
      fullPrice: { color: C.muted },
      discount: lineItemText,
      discountIcon: { fill: C.text },
      quantity: lineItemText,
      quantityIncrement: { color: C.text, 'border-color': C.line },
      quantityDecrement: { color: C.text, 'border-color': C.line },
      quantityInput: { color: C.text, 'border-color': C.line, 'background-color': C.elevated },
    },
  },
}

// Shopify keeps one cart for the page and its events from the first mount,
// so they call whichever Apparel view is showing now
let cartListener = null
const CART_EVENTS = {
  afterInit: (c) => cartListener?.(c),
  afterRender: (c) => cartListener?.(c),
}

let sdkPromise = null
function loadSdk() {
  if (window.ShopifyBuy?.UI) return Promise.resolve(window.ShopifyBuy)
  if (!sdkPromise) {
    sdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.async = true
      script.src = SDK_URL
      script.onload = () => resolve(window.ShopifyBuy)
      script.onerror = () => { sdkPromise = null; reject(new Error('Shopify did not load')) }
      document.head.appendChild(script)
    })
  }
  return sdkPromise
}

// What the apparel cart holds, read from Shopify's cart: { count, subtotalCents }
export function cartSummary(cart) {
  const items = cart?.model?.lineItems || []
  const count = items.reduce((n, item) => n + (item.quantity || 0), 0)
  const amount = cart?.model?.lineItemsSubtotalPrice?.amount
  return { count, subtotalCents: Math.round(parseFloat(amount || 0) * 100) }
}

export default function ShopifyApparel() {
  const node = useRef(null)
  const ui = useRef(null)
  const [failed, setFailed] = useState(false)
  const [cart, setCart] = useState({ count: 0, subtotalCents: 0 })

  useEffect(() => {
    let cancelled = false
    loadSdk()
      .then((ShopifyBuy) => {
        if (cancelled || !node.current) return null
        const client = ShopifyBuy.buildClient(SHOP)
        return ShopifyBuy.UI.onReady(client).then((shopifyUi) => {
          if (cancelled || !node.current) return
          ui.current = shopifyUi
          node.current.innerHTML = ''
          // Shopify's floating cart tab is hidden (index.css); our bar below
          // shows the cart instead and opens Shopify's cart for checkout
          cartListener = (c) => setCart(cartSummary(c))
          const drawn = shopifyUi.createComponent('product', {
            id: PRODUCT_ID,
            node: node.current,
            moneyFormat: '%24%7B%7Bamount%7D%7D',
            options: {
              ...BUY_BUTTON_OPTIONS,
              cart: {
                ...BUY_BUTTON_OPTIONS.cart,
                events: CART_EVENTS,
              },
            },
          })
          // Shopify's hosted build doesn't always return a promise here, and
          // nothing after drawing may hide a shirt that's already showing
          Promise.resolve(drawn)
            .then(() => {
              const existing = shopifyUi.components?.cart?.[0]
              if (!cancelled && existing?.model) setCart(cartSummary(existing))
            })
            .catch(() => {})
        })
      })
      .catch(() => { if (!cancelled) setFailed(true) })
    const current = node.current
    return () => {
      cancelled = true
      cartListener = null
      ui.current?.closeCart()
      if (current) current.innerHTML = ''
    }
  }, [])

  return (
    <section aria-labelledby="apparel-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 id="apparel-heading" className="text-2xl font-display text-secondary">Apparel</h2>
        <span className="text-xs uppercase tracking-wider text-text-muted">Explorer Series shirts</span>
      </div>
      <p className="text-sm text-text-muted mb-6 max-w-3xl">
        Apparel has its own cart and checks out on the Explorer Series Shopify store, separate from
        the other store tabs. Add your jersey name in the apparel cart&apos;s note before checking out.
      </p>
      {failed ? (
        <p className="text-sm text-text-muted">
          The apparel shop couldn&apos;t load right now. Please refresh the page to try again.
        </p>
      ) : (
        <div ref={node} data-testid="shopify-apparel" className="min-h-[120px]" />
      )}

      {cart.count > 0 && (
        <div className="sticky bottom-4 mt-8 bg-bg-elevated border border-secondary/30 rounded-lg p-4 flex items-center justify-between gap-3 shadow-harsh">
          <div className="text-sm">
            <span className="block text-xs text-text-muted mb-0.5">Apparel cart</span>
            <span className="font-medium text-text-primary">
              {cart.count} {cart.count === 1 ? 'item' : 'items'}
            </span>
            {' '}&middot;{' '}
            <span className="text-secondary font-semibold">{formatMoney(cart.subtotalCents)}</span>
            <span className="text-text-muted ml-1.5 hidden sm:inline">+ shipping on Shopify</span>
          </div>
          <button
            type="button"
            onClick={() => ui.current?.openCart()}
            className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors flex items-center gap-2 whitespace-nowrap"
          >
            View cart
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        </div>
      )}
    </section>
  )
}
