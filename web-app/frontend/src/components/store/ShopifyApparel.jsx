import { useEffect, useRef, useState } from 'react'
import { formatMoney } from '@/api/store'
import { splitDescription } from './apparelDetails'

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
// The Explorer team's apparel listings, in the order Bruce sent their
// Buy Button codes (2026-10-19). Prices, colors and photos come from Shopify.
export const PRODUCT_IDS = [
  '9692531622127',
  '9692532900079',
  '9692534046959',
  '9692534276335',
  '9692535161071',
]

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
// Light behind the photos: product shots with a transparent background (a
// dark shirt cut out of its photo) vanish on our dark cards otherwise, and
// Shopify's carousel arrows are dark too
const imgWrapper = { 'background-color': '#ffffff', 'border-radius': '8px', padding: '8px', 'margin-bottom': '16px' }

export const BUY_BUTTON_OPTIONS = {
  product: {
    styles: {
      product: {
        '@media (min-width: 601px)': {
          'max-width': '100%',
          'margin-left': '0',
          'margin-bottom': '0',
        },
        'text-align': 'left',
      },
      title: { 'font-family': FONT, 'font-size': '18px', 'font-weight': '600', color: C.text },
      price: { 'font-family': FONT, 'font-size': '16px', 'font-weight': '600', color: C.gold },
      compareAt: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      unitPrice: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      description: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      imgWrapper,
      button,
      quantityInput,
      // Shopify's own sheet paints the box beside the button white with a
      // more specific selector; nesting matches it so ours wins
      buttonWithQuantity: { quantityInput },
    },
    buttonDestination: 'cart',
    layout: 'vertical',
    width: '100%',
    // The description shows under each card in fold-out sections instead
    contents: { img: false, imgWithCarousel: true, button: false, buttonWithQuantity: true, description: false },
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
      imgWrapper,
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
      title: 'Explorer Apparel cart',
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
// Shopify's cart itself, as handed to its events. The object onReady gives
// back from Shopify's hosted build doesn't reliably have openCart, so the bar
// opens and closes this instead
let shopifyCart = null
const onCart = (c) => {
  shopifyCart = c
  cartListener?.(c)
}
const CART_EVENTS = { afterInit: onCart, afterRender: onCart }

// Hands each listing's description to the card it belongs to
let detailsListener = null
const PRODUCT_EVENTS = {
  afterInit: (p) => {
    const id = String(p?.model?.id || '').split('/').pop()
    if (id) detailsListener?.(id, p.model.descriptionHtml || p.model.description || '')
  },
}

function openCartNow() {
  if (typeof shopifyCart?.open === 'function') shopifyCart.open()
  else if (typeof shopifyCart?.toggleVisibility === 'function') shopifyCart.toggleVisibility(true)
}

// Shopify closes its cart on any click outside it, including the click on
// our View cart button, so open it once that click has finished
export function openShopifyCart() {
  setTimeout(openCartNow, 0)
}

function closeShopifyCart() {
  try {
    if (shopifyCart?.isVisible && typeof shopifyCart.close === 'function') shopifyCart.close()
  } catch {
    // leaving the tab must never fail over a cart drawer
  }
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

function Fold({ title, html, plain = false }) {
  if (!html) return null
  return (
    <details className="group border-t border-border">
      <summary className="flex items-center justify-between py-3 cursor-pointer list-none text-sm font-semibold text-text-primary hover:text-secondary [&::-webkit-details-marker]:hidden">
        {title}
        <svg className="transition-transform group-open:rotate-180" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </summary>
      <div
        className={`pb-3 text-sm text-text-muted space-y-2 overflow-x-auto ${plain ? '[&_ul]:list-none [&_ol]:list-none' : '[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5'} [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_h4]:font-semibold [&_h5]:font-semibold [&_h6]:font-semibold [&_strong]:text-text [&_table]:w-full [&_table]:text-xs [&_th]:text-left [&_th]:font-semibold [&_th]:text-text [&_th]:px-1.5 [&_th]:py-1 [&_td]:px-1.5 [&_td]:py-1 [&_tr]:border-b [&_tr]:border-border/60`}
        // Cleaned to plain formatting tags with no attributes (apparelDetails.js)
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </details>
  )
}

export default function ShopifyApparel() {
  const node = useRef(null)
  const slots = useRef({})
  const [failed, setFailed] = useState(false)
  const [cart, setCart] = useState({ count: 0, subtotalCents: 0 })
  const [details, setDetails] = useState({}) // { productId: { details, sizeChart } }

  useEffect(() => {
    let cancelled = false
    loadSdk()
      .then((ShopifyBuy) => {
        if (cancelled || !node.current) return null
        const client = ShopifyBuy.buildClient(SHOP)
        return ShopifyBuy.UI.onReady(client).then((shopifyUi) => {
          if (cancelled || !node.current) return
          // Shopify's floating cart tab is hidden (index.css); our bar below
          // shows the cart instead and opens Shopify's cart for checkout
          cartListener = (c) => setCart(cartSummary(c))
          detailsListener = (id, html) => setDetails((d) => ({ ...d, [id]: splitDescription(html) }))
          // Every listing shares Shopify's one cart
          const drawn = PRODUCT_IDS.map((id) => {
            const slot = slots.current[id]
            if (!slot) return null
            slot.innerHTML = ''
            return shopifyUi.createComponent('product', {
              id,
              node: slot,
              moneyFormat: '%24%7B%7Bamount%7D%7D',
              options: {
                ...BUY_BUTTON_OPTIONS,
                product: { ...BUY_BUTTON_OPTIONS.product, events: PRODUCT_EVENTS },
                cart: {
                  ...BUY_BUTTON_OPTIONS.cart,
                  events: CART_EVENTS,
                },
              },
            })
          })
          // Shopify's hosted build doesn't always return a promise here, and
          // nothing after drawing may hide a listing that's already showing
          Promise.all(drawn.map((d) => Promise.resolve(d).catch(() => null)))
            .then(() => {
              // Coming back to the tab: the cart already exists, so no event fires
              if (!cancelled && shopifyCart?.model) setCart(cartSummary(shopifyCart))
            })
            .catch(() => {})
        })
      })
      .catch(() => { if (!cancelled) setFailed(true) })
    const current = slots.current
    return () => {
      cancelled = true
      cartListener = null
      detailsListener = null
      closeShopifyCart()
      Object.values(current).forEach((slot) => { if (slot) slot.innerHTML = '' })
    }
  }, [])

  return (
    <section aria-labelledby="apparel-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 id="apparel-heading" className="text-2xl font-display text-secondary">Explorer Apparel</h2>
        <span className="text-xs uppercase tracking-wider text-text-muted">Explorer Series</span>
      </div>
      <p className="text-sm text-text-muted mb-6 max-w-3xl">
        Explorer Apparel has its own cart and checks out on the Explorer Series Shopify store, separate from
        the other store tabs. Add your jersey name in the apparel cart&apos;s note before checking out.
      </p>
      {failed ? (
        <p className="text-sm text-text-muted">
          The apparel shop couldn&apos;t load right now. Please refresh the page to try again.
        </p>
      ) : (
        <div ref={node} data-testid="shopify-apparel" className="min-h-[120px] grid gap-5 sm:grid-cols-2 lg:grid-cols-3 items-start">
          {PRODUCT_IDS.map((id) => (
            <div key={id} className="bg-bg-surface border border-border rounded-lg p-4">
              <div ref={(el) => { slots.current[id] = el }} />
              {(details[id]?.details || details[id]?.sizeChart) && (
                <div className="mt-2">
                  <Fold title="Details" html={details[id].details} />
                  <Fold title="Size chart" html={details[id].sizeChart} plain />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {cart.count > 0 && (
        <div className="sticky bottom-4 mt-8 bg-bg-elevated border border-secondary/30 rounded-lg p-4 flex items-center justify-between gap-3 shadow-harsh">
          <div className="text-sm">
            <span className="block text-xs text-text-muted mb-0.5">Explorer Apparel cart</span>
            <span className="font-medium text-text-primary">
              {cart.count} {cart.count === 1 ? 'item' : 'items'}
            </span>
            {' '}&middot;{' '}
            <span className="text-secondary font-semibold">{formatMoney(cart.subtotalCents)}</span>
            <span className="text-text-muted ml-1.5 hidden sm:inline">+ shipping on Shopify</span>
          </div>
          <button
            type="button"
            onClick={openShopifyCart}
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
