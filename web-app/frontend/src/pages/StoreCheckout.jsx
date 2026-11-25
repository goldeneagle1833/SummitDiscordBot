import { useState, useEffect } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import {
  getProducts, getPrivateProduct, getCheckoutPrefill, createCheckout, formatMoney, previewTicketReset,
} from '@/api/store'
import { DEFAULT_STOREFRONT, loadCart, saveCart, reconcileCart, maxQuantity } from '@/hooks/useStoreCart'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import { DEFAULT_SHIPPING_RULES, cartShipping, shippingLabel } from '@/utils/storeShipping'

// Late-ticket reset: shown before paying when this season's ticket would
// drop some of the buyer's season ratings to 1500.
export function TicketResetWarning({ warning, onCancel, onConfirm }) {
  const [agreed, setAgreed] = useState(false)
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onCancel])

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60 p-4" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="ticket-reset-title"
        className="bg-bg-surface border border-border rounded-lg w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 space-y-4">
          <h3 id="ticket-reset-title" className="text-lg font-display text-secondary">
            Heads up: your ratings will reset
          </h3>
          <p className="text-sm">
            We're past the first week of <span className="font-semibold">{warning.event_name}</span>, so
            buying a ticket now sets your season ratings above {warning.cap} to {warning.cap}:
          </p>
          <ul className="rounded-lg border border-border bg-bg-elevated divide-y divide-border text-sm">
            {warning.entries.map((e) => (
              <li key={e.avatar || 'season'} className="flex items-center justify-between px-4 py-2">
                <span className="font-medium">{e.avatar || 'Season rating'}</span>
                <span>
                  <span className="text-text-muted line-through mr-2">{e.from}</span>
                  <span className="text-secondary font-semibold">{e.to}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-text-muted">
            Anything at or below {warning.cap} stays where it is. Your games, wins and losses don't change.
          </p>
          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
            />
            <span>I understand my ratings above {warning.cap} will be set to {warning.cap}.</span>
          </label>
          <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-1">
            <button
              onClick={onCancel}
              className="px-4 py-2.5 rounded-lg border border-border text-sm hover:border-primary/50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={!agreed}
              className="px-4 py-2.5 rounded-lg bg-secondary text-black text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Continue anyway
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function CheckoutProgress({ step }) {
  const steps = ['Review', 'Payment', 'Confirmation']
  return (
    <div className="flex items-center justify-center gap-1 mb-8">
      {steps.map((label, i) => {
        const stepNum = i + 1
        const active = stepNum === step
        const done = stepNum < step
        return (
          <div key={label} className="flex items-center gap-1">
            {i > 0 && (
              <div className={`w-8 sm:w-12 h-px ${done ? 'bg-secondary' : 'bg-border'}`} />
            )}
            <div className="flex items-center gap-1.5">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  done
                    ? 'bg-secondary text-black'
                    : active
                      ? 'bg-secondary/20 text-secondary border border-secondary'
                      : 'bg-bg-elevated text-text-muted border border-border'
                }`}
              >
                {done ? (
                  <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                ) : (
                  stepNum
                )}
              </div>
              <span className={`text-xs font-medium hidden sm:inline ${active ? 'text-text-primary' : 'text-text-muted'}`}>
                {label}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function StoreCheckout() {
  usePageTitle('Checkout')
  const { user, loading: authLoading } = useAuth()
  const [params] = useSearchParams()
  // Each storefront checks out on its own, from its own cart
  const storefront = params.get('storefront') || DEFAULT_STOREFRONT
  // A private (link only) listing checks out on its own, outside the cart
  const privateToken = params.get('private')
  const privateQty = parseInt(params.get('qty') || '1', 10)
  const storeUrl = privateToken
    ? `/store/p/${encodeURIComponent(privateToken)}`
    : storefront === DEFAULT_STOREFRONT
      ? '/store'
      : `/store?storefront=${encodeURIComponent(storefront)}`

  const [items, setItems] = useState([])
  const [email, setEmail] = useState('')
  const [freeShipping, setFreeShipping] = useState(false)
  const [shippingRules, setShippingRules] = useState(DEFAULT_SHIPPING_RULES)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [resetWarning, setResetWarning] = useState(null)

  const isGoogleUser = user?.auth_provider && user.auth_provider !== 'discord'

  useEffect(() => {
    if (!user) return
    // Build the order from the saved cart and current product data, so a
    // refresh keeps the cart and prices/stock/limits are never stale.
    const loadItems = privateToken
      ? getPrivateProduct(privateToken).then((data) => {
        const p = data.product
        if (data.shipping_rules) setShippingRules(data.shipping_rules)
        const quantity = Math.min(Number.isFinite(privateQty) && privateQty > 0 ? privateQty : 1, maxQuantity(p))
        setItems(quantity > 0 ? [{
          product_id: p.id,
          quantity,
          private_token: privateToken,
          name: p.name,
          price_cents: p.price_cents,
          ship_cards: p.ship_cards,
          shipping_cents: p.shipping_cents,
        }] : [])
      })
      : getProducts().then((data) => {
        const products = data.products || []
        if (data.shipping_rules) setShippingRules(data.shipping_rules)
        const cart = reconcileCart(loadCart(storefront), products)
        saveCart(cart, storefront)
        setItems(
          products
            .filter((p) => cart[p.id])
            .map((p) => ({
              product_id: p.id,
              quantity: cart[p.id],
              name: p.name,
              price_cents: p.price_cents,
              ship_cards: p.ship_cards,
              shipping_cents: p.shipping_cents,
              role_only: p.product_type === 'discord_role',
            })),
        )
      })
    Promise.all([
      loadItems,
      getCheckoutPrefill()
        .then((pre) => {
          if (pre.email) setEmail(pre.email)
          if (pre.free_shipping) setFreeShipping(true)
        })
        .catch(() => {}),
    ])
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [user, storefront, privateToken, privateQty])

  if (authLoading) return <Spinner className="py-20" />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(storeUrl)}`} replace />
  if (loading) return <Spinner className="py-20" />
  if (error && items.length === 0) {
    return <p className="text-center text-accent-red py-8">{error}</p>
  }
  if (items.length === 0) return <Navigate to={storeUrl} replace />

  const subtotal = items.reduce((s, i) => s + i.price_cents * i.quantity, 0)
  const digitalOnly = items.length > 0 && items.every((i) => i.role_only)
  // Known before payment when every listing has its shipping set
  const shipping = freeShipping || digitalOnly
    ? null
    : cartShipping(items.map((i) => ({ product: i, quantity: i.quantity })), shippingRules)

  const isValidEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)

  const submit = async ({ resetAcknowledged = false } = {}) => {
    setError(null)
    const trimmed = email.trim()
    if (trimmed && !isValidEmail(trimmed)) {
      setError('Please enter a valid email address.')
      return
    }
    if (isGoogleUser && !trimmed) {
      setError('Email address is required.')
      return
    }
    setSubmitting(true)
    if (!resetAcknowledged) {
      // Late ticket? Show what it does to their ratings before they pay.
      const preview = await previewTicketReset(items.map((i) => i.product_id)).catch(() => null)
      if (preview?.will_reset) {
        setResetWarning(preview)
        setSubmitting(false)
        return
      }
    }
    try {
      const { checkout_url } = await createCheckout({
        items: items.map(({ product_id, quantity, private_token }) => (
          private_token ? { product_id, quantity, private_token } : { product_id, quantity })),
        email: trimmed || undefined,
      })
      window.location.assign(checkout_url)
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  const inputCls =
    'w-full rounded-lg border border-border bg-bg-surface px-3 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors'

  return (
    <div className="max-w-2xl mx-auto">
      <CheckoutProgress step={1} />

      <h1 className="text-2xl font-display text-secondary mb-6">Review your order</h1>

      {/* Order summary */}
      <div className="bg-bg-surface border border-border rounded-lg overflow-hidden mb-6">
        <div className="px-4 py-3 bg-bg-elevated border-b border-border">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wide">Order Summary</h2>
        </div>
        <div className="p-4">
          {items.map((i) => (
            <div key={i.product_id} className="flex justify-between items-center py-2">
              <div className="flex items-center gap-3">
                <span className="w-7 h-7 rounded bg-bg-elevated flex items-center justify-center text-xs font-medium text-text-muted">
                  {i.quantity}x
                </span>
                <span className="text-sm font-medium text-text-primary">{i.name}</span>
              </div>
              <span className="text-sm font-medium">{formatMoney(i.price_cents * i.quantity)}</span>
            </div>
          ))}
          <div className="flex justify-between items-center pt-3 mt-3 border-t border-border">
            <span className="text-sm text-text-muted">Subtotal</span>
            <span className="text-secondary font-semibold">{formatMoney(subtotal)}</span>
          </div>
          {shipping ? (
            <>
              <div className="flex justify-between items-center pt-2">
                <span className="text-sm text-text-muted">
                  Shipping
                  <span className="block text-xs">{shippingLabel(shipping, shippingRules)}</span>
                </span>
                <span className="text-sm font-medium">{formatMoney(shipping.cents)}</span>
              </div>
              <div className="flex justify-between items-center pt-2 mt-2 border-t border-border">
                <span className="text-sm font-semibold">Total</span>
                <span className="text-secondary font-semibold">{formatMoney(subtotal + shipping.cents)}</span>
              </div>
              {shipping.method === 'envelope' && (
                <p className="text-xs text-text-muted mt-2">
                  Add more than {shippingRules.envelope_max_cards} cards and it ships USPS Ground Advantage
                  for {formatMoney(shippingRules.ground_cents)}.
                </p>
              )}
            </>
          ) : (
            <p className="text-xs text-text-muted mt-2">
              {digitalOnly
                ? 'No shipping. The Summit bot adds your Discord role after payment.'
                : freeShipping
                  ? 'Free shipping \u2014 thank you for your support!'
                  : 'Shipping calculated at payment'}
            </p>
          )}
        </div>
      </div>

      {/* Contact info */}
      <div className="bg-bg-surface border border-border rounded-lg overflow-hidden mb-6">
        <div className="px-4 py-3 bg-bg-elevated border-b border-border">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wide">Contact</h2>
        </div>
        <div className="p-4">
          <input
            className={inputCls}
            placeholder={isGoogleUser ? 'Email (required)' : 'Email for updates (optional)'}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <p className="text-xs text-text-muted mt-2">
            {isGoogleUser
              ? "Order updates and tracking go to this email."
              : "You'll get order updates by Discord DM. Add an email as backup if your DMs are closed."}
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-lg px-4 py-3 mb-4">
          <p className="text-accent-red text-sm">{error}</p>
        </div>
      )}

      {/* CTA */}
      <button
        onClick={() => submit()}
        disabled={submitting}
        className="w-full bg-primary hover:bg-primary-dark text-white font-semibold py-3 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2 text-base"
      >
        {submitting ? (
          'Redirecting to Stripe...'
        ) : (
          <>
            Continue to payment
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </>
        )}
      </button>

      <div className="flex items-center justify-center gap-2 mt-4 text-text-muted">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        <span className="text-xs">Secure checkout powered by Stripe</span>
      </div>

      <div className="text-center mt-3">
        <Link to={storeUrl} className="text-sm text-text-muted hover:text-text transition-colors">
          &larr; {privateToken ? 'Back to the listing' : 'Back to store'}
        </Link>
      </div>

      {resetWarning && (
        <TicketResetWarning
          warning={resetWarning}
          onCancel={() => setResetWarning(null)}
          onConfirm={() => { setResetWarning(null); submit({ resetAcknowledged: true }) }}
        />
      )}
    </div>
  )
}
