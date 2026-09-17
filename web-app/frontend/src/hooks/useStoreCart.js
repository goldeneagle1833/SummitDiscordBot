import { useState, useEffect } from 'react'

// Per-tab cart ({ [productId]: quantity }). sessionStorage survives the
// OAuth sign-in round trip, page refreshes, and a cancelled Stripe checkout.
export const CART_KEY = 'summit-store-cart'

export function loadCart() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(CART_KEY) || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed).filter(([, qty]) => Number.isInteger(qty) && qty > 0),
    )
  } catch {
    return {}
  }
}

export function saveCart(cart) {
  try {
    if (Object.keys(cart).length === 0) sessionStorage.removeItem(CART_KEY)
    else sessionStorage.setItem(CART_KEY, JSON.stringify(cart))
  } catch {
    // Storage unavailable (private mode, blocked): cart just won't persist
  }
}

export function clearCart() {
  try {
    sessionStorage.removeItem(CART_KEY)
  } catch {
    // ignore
  }
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

export default function useStoreCart() {
  const [cart, setCart] = useState(loadCart)
  useEffect(() => saveCart(cart), [cart])
  return [cart, setCart]
}
