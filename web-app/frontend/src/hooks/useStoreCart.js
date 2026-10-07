import { useState, useEffect } from 'react'

// Per-tab carts ({ [productId]: quantity }), one per storefront, because each
// storefront checks out as its own order. sessionStorage survives the OAuth
// sign-in round trip, page refreshes, and a cancelled Stripe checkout.
export const CART_KEY = 'summit-store-cart'
export const DEFAULT_STOREFRONT = 'summit'

// The Summit cart keeps the original key so carts saved before storefronts
// existed are still there.
export const cartKey = (slug = DEFAULT_STOREFRONT) =>
  !slug || slug === DEFAULT_STOREFRONT ? CART_KEY : `${CART_KEY}:${slug}`

export function loadCart(slug) {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(cartKey(slug)) || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed).filter(([, qty]) => Number.isInteger(qty) && qty > 0),
    )
  } catch {
    return {}
  }
}

export function saveCart(cart, slug) {
  try {
    if (Object.keys(cart).length === 0) sessionStorage.removeItem(cartKey(slug))
    else sessionStorage.setItem(cartKey(slug), JSON.stringify(cart))
  } catch {
    // Storage unavailable (private mode, blocked): cart just won't persist
  }
}

export function clearCart(slug) {
  try {
    sessionStorage.removeItem(cartKey(slug))
  } catch {
    // ignore
  }
}

export function cartCount(slug) {
  return Object.values(loadCart(slug)).reduce((n, qty) => n + qty, 0)
}

// Most of a product this buyer can put in the cart: stock, capped by what's
// left of their monthly limit (only sent by the API for logged-in buyers).
export function maxQuantity(product) {
  return Math.max(0, Math.min(product.stock_quantity, product.remaining_this_month ?? Infinity))
}

// Drop products that are no longer for sale and clamp quantities to what can
// actually be bought right now.
export function reconcileCart(cart, products) {
  const next = {}
  for (const p of products) {
    const qty = Math.min(cart[p.id] || 0, maxQuantity(p))
    if (qty > 0) next[p.id] = qty
  }
  return next
}

export default function useStoreCart(slug = DEFAULT_STOREFRONT) {
  const [state, setState] = useState(() => ({ slug, cart: loadCart(slug) }))
  // Switching storefront tabs swaps in that storefront's cart
  if (state.slug !== slug) setState({ slug, cart: loadCart(slug) })
  useEffect(() => saveCart(state.cart, state.slug), [state])
  const setCart = (update) =>
    setState((s) => ({ ...s, cart: typeof update === 'function' ? update(s.cart) : update }))
  return [state.slug === slug ? state.cart : loadCart(slug), setCart]
}
