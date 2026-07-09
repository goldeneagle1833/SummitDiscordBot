import { useState, useEffect } from 'react'
import { Link, useLocation, Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { getCheckoutPrefill, createCheckout, formatMoney } from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const EMPTY = { name: '', line1: '', line2: '', city: '', state: '', postal: '', country: 'US' }

export default function StoreCheckout() {
  usePageTitle('Checkout')
  const { user } = useAuth()
  const location = useLocation()
  const items = location.state?.items || []

  const [address, setAddress] = useState(EMPTY)
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const isGoogleUser = user?.auth_provider && user.auth_provider !== 'discord'

  useEffect(() => {
    getCheckoutPrefill()
      .then((pre) => {
        if (pre.address) setAddress((a) => ({ ...a, ...pre.address }))
        else if (pre.name) setAddress((a) => ({ ...a, name: pre.name }))
        if (pre.email) setEmail(pre.email)
      })
      .catch(() => {}) // prefill is best-effort
      .finally(() => setLoading(false))
  }, [])

  if (items.length === 0) return <Navigate to="/store" replace />
  if (loading) return <Spinner className="py-20" />

  const subtotal = items.reduce((s, i) => s + i.price_cents * i.quantity, 0)
  const set = (field) => (e) => setAddress((a) => ({ ...a, [field]: e.target.value }))

  const submit = async () => {
    setError(null)
    setSubmitting(true)
    try {
      const { checkout_url } = await createCheckout({
        items: items.map(({ product_id, quantity }) => ({ product_id, quantity })),
        shipping_address: address,
        email: email.trim() || undefined,
      })
      window.location.assign(checkout_url) // hand off to Stripe's hosted page
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  const inputCls =
    'w-full rounded border border-border bg-bg-surface px-3 py-2 text-sm focus:outline-none focus:border-primary'

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-display text-secondary mb-4">Checkout</h1>

      <div className="bg-bg-surface border border-border rounded-lg p-4 mb-6">
        <h2 className="font-semibold mb-2">Your order</h2>
        {items.map((i) => (
          <div key={i.product_id} className="flex justify-between text-sm py-1">
            <span>
              {i.quantity}x {i.name}
            </span>
            <span>{formatMoney(i.price_cents * i.quantity)}</span>
          </div>
        ))}
        <div className="flex justify-between text-sm pt-2 mt-2 border-t border-border">
          <span className="text-text-muted">Subtotal (shipping added at payment)</span>
          <span className="text-secondary font-medium">{formatMoney(subtotal)}</span>
        </div>
      </div>

      <h2 className="font-semibold mb-3">Shipping address</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <input className={`${inputCls} sm:col-span-2`} placeholder="Full name" value={address.name} onChange={set('name')} autoComplete="name" />
        <input className={`${inputCls} sm:col-span-2`} placeholder="Street address" value={address.line1} onChange={set('line1')} autoComplete="address-line1" />
        <input className={`${inputCls} sm:col-span-2`} placeholder="Apt, suite, etc. (optional)" value={address.line2 || ''} onChange={set('line2')} autoComplete="address-line2" />
        <input className={inputCls} placeholder="City" value={address.city} onChange={set('city')} autoComplete="address-level2" />
        <input className={inputCls} placeholder="State" value={address.state} onChange={set('state')} autoComplete="address-level1" />
        <input className={inputCls} placeholder="ZIP code" value={address.postal} onChange={set('postal')} autoComplete="postal-code" />
        <input
          className={inputCls}
          placeholder={isGoogleUser ? 'Email (required)' : 'Email for updates (optional)'}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
        />
      </div>
      <p className="text-xs text-text-muted mt-2">
        {isGoogleUser
          ? "Order updates and tracking go to this email."
          : "You'll get order updates by Discord DM. Add an email as backup if your DMs are closed."}
      </p>

      {error && <p className="text-accent-red text-sm mt-3">{error}</p>}

      <div className="flex items-center gap-3 mt-5">
        <button
          onClick={submit}
          disabled={submitting}
          className="bg-primary hover:bg-primary-dark text-white font-medium px-6 py-2.5 rounded transition-colors disabled:opacity-50"
        >
          {submitting ? 'Starting payment…' : 'Continue to payment'}
        </button>
        <Link to="/store" className="text-sm text-text-muted hover:text-text">
          Back to store
        </Link>
      </div>
      <p className="text-xs text-text-muted mt-3">
        Payment is handled securely by Stripe. Your card details never touch our servers.
      </p>
    </div>
  )
}
