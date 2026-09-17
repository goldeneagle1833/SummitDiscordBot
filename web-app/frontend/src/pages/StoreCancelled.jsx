import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { cancelMyOrder } from '@/api/store'
import usePageTitle from '@/hooks/usePageTitle'

export default function StoreCancelled() {
  usePageTitle('Checkout cancelled')
  const { user, loading: authLoading } = useAuth()
  const [params] = useSearchParams()
  const orderNumber = params.get('order')
  // releasing | released | paid | unknown
  const [release, setRelease] = useState(orderNumber ? 'releasing' : 'unknown')

  // Cancel the pending order now so its stock and the buyer's monthly limit
  // are freed immediately, instead of when the Stripe session expires.
  useEffect(() => {
    if (!orderNumber || authLoading) return
    if (!user) {
      setRelease('unknown')
      return
    }
    let ignore = false
    cancelMyOrder(orderNumber)
      .then(() => !ignore && setRelease('released'))
      .catch((err) => !ignore && setRelease(err.status === 409 ? 'paid' : 'unknown'))
    return () => {
      ignore = true
    }
  }, [orderNumber, user, authLoading])

  if (release === 'paid') {
    return (
      <div className="max-w-lg mx-auto text-center py-16">
        <h1 className="text-2xl font-display text-secondary mb-2">Your payment went through</h1>
        <p className="text-text-muted mb-8">
          Order <span className="font-mono">{orderNumber}</span> was paid before the checkout
          was closed, so it hasn&apos;t been cancelled.
        </p>
        <Link
          to="/store/orders"
          className="inline-flex items-center gap-2 bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors"
        >
          View my orders
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-lg mx-auto text-center py-16">
      <div className="w-16 h-16 rounded-full bg-bg-elevated border border-border flex items-center justify-center mx-auto mb-5">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <path d="M9 9l10 10M19 9L9 19" stroke="#8b949e" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      </div>

      <h1 className="text-2xl font-display text-secondary mb-2">Checkout cancelled</h1>
      <p className="text-text-muted mb-2">
        No payment was taken{orderNumber ? <> for order <span className="font-mono">{orderNumber}</span></> : ''}.
      </p>
      <p className="text-text-muted text-sm mb-8">
        {release === 'releasing' && 'Releasing your items…'}
        {release === 'released' && 'Your items have been released. Your cart is saved, so you can pick up where you left off.'}
        {release === 'unknown' && 'Your cart is saved. Any reserved items are released automatically within an hour.'}
      </p>
      <Link
        to="/store"
        className="inline-flex items-center gap-2 bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
        Back to store
      </Link>
    </div>
  )
}
