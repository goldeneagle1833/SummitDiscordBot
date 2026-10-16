import { useEffect, useRef, useState } from 'react'

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
const COLLECTION_ID = '505064325359'

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
  'padding-top': '12px',
  'padding-bottom': '12px',
  color: C.text,
  'background-color': C.elevated,
  'border-color': C.line,
}
const lineItemText = { color: C.text }

export const BUY_BUTTON_OPTIONS = {
  product: {
    styles: {
      product: {
        '@media (min-width: 601px)': {
          'max-width': 'calc(33.333% - 20px)',
          'margin-left': '20px',
          'margin-bottom': '40px',
          width: 'calc(33.333% - 20px)',
        },
      },
      title: { 'font-family': FONT, 'font-size': '17px', 'font-weight': '600', color: C.text },
      price: { 'font-family': FONT, 'font-size': '16px', 'font-weight': '600', color: C.gold },
      compareAt: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      unitPrice: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      description: { 'font-family': FONT, 'font-size': '14px', color: C.muted },
      button,
      quantityInput,
    },
    buttonDestination: 'cart',
    contents: { img: false, imgWithCarousel: true, button: false, buttonWithQuantity: true },
    text: { button: 'Add to cart' },
    googleFonts: ['Figtree'],
  },
  productSet: {
    styles: { products: { '@media (min-width: 601px)': { 'margin-left': '-20px' } } },
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

export default function ShopifyApparel() {
  const node = useRef(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    loadSdk()
      .then((ShopifyBuy) => {
        if (cancelled || !node.current) return null
        const client = ShopifyBuy.buildClient(SHOP)
        return ShopifyBuy.UI.onReady(client).then((ui) => {
          if (cancelled || !node.current) return
          node.current.innerHTML = ''
          ui.createComponent('collection', {
            id: COLLECTION_ID,
            node: node.current,
            moneyFormat: '%24%7B%7Bamount%7D%7D',
            options: BUY_BUTTON_OPTIONS,
          })
        })
      })
      .catch(() => { if (!cancelled) setFailed(true) })
    const current = node.current
    return () => {
      cancelled = true
      if (current) current.innerHTML = ''
    }
  }, [])

  return (
    <section aria-labelledby="apparel-heading" className="mt-14 pt-10 border-t border-border/60">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 id="apparel-heading" className="text-2xl font-display text-secondary">Apparel</h2>
        <span className="text-xs uppercase tracking-wider text-text-muted">Explorer Series shirts</span>
      </div>
      <p className="text-sm text-text-muted mb-6 max-w-3xl">
        Apparel has its own cart and checks out on the Explorer Series Shopify store, separate from
        the cart above. Add your jersey name in the apparel cart&apos;s note before checking out.
      </p>
      {failed ? (
        <p className="text-sm text-text-muted">
          The apparel shop couldn&apos;t load right now. Please refresh the page to try again.
        </p>
      ) : (
        <div ref={node} data-testid="shopify-apparel" className="min-h-[120px]" />
      )}
    </section>
  )
}
