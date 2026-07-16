import { useState, useEffect } from 'react'
import { Link, useLocation, Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { getCheckoutPrefill, createCheckout, formatMoney } from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

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
  const { user } = useAuth()
  const location = useLocation()
  const items = location.state?.items || []

  const [email, setEmail] = useState('')
  const [freeShipping, setFreeShipping] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const isGoogleUser = user?.auth_provider && user.auth_provider !== 'discord'

  useEffect(() => {
    getCheckoutPrefill()
      .then((pre) => {
        if (pre.email) setEmail(pre.email)
        if (pre.free_shipping) setFreeShipping(true)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (!user) return <Navigate to={`/login?next=${encodeURIComponent('/store')}`} replace />
  if (items.length === 0) return <Navigate to="/store" replace />
  if (loading) return <Spinner className="py-20" />

  const subtotal = items.reduce((s, i) => s + i.price_cents * i.quantity, 0)

  const submit = async () => {
    setError(null)
    setSubmitting(true)
    try {
      const { checkout_url } = await createCheckout({
        items: items.map(({ product_id, quantity }) => ({ product_id, quantity })),
        email: email.trim() || undefined,
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
          <p className="text-xs text-text-muted mt-2">
            {freeShipping
              ? 'Free shipping \u2014 thank you for your support!'
              : 'Shipping calculated at payment'}
          </p>
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
        onClick={submit}
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
        <Link to="/store" className="text-sm text-text-muted hover:text-text transition-colors">
          &larr; Back to store
        </Link>
      </div>
    </div>
  )
}
