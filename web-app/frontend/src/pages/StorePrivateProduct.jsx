import { useState, useEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { getPrivateProduct, formatMoney } from '@/api/store'
import { maxQuantity } from '@/hooks/useStoreCart'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import { DEFAULT_SHIPPING_RULES, cartShipping, shippingLabel } from '@/utils/storeShipping'
import { LoginPromptModal, ProductGallery } from '@/pages/Store'

// A private (link only) listing: not on /store, opened from its own link or
// QR code. Bought on its own, without touching the buyer's cart.
export default function StorePrivateProduct() {
  const { token } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState(null)
  const [qty, setQty] = useState(1)
  const [showLoginPrompt, setShowLoginPrompt] = useState(false)
  usePageTitle(data?.product?.name || 'Store')

  useEffect(() => {
    let ignore = false
    getPrivateProduct(token)
      .then((d) => !ignore && setData(d))
      .catch((err) => {
        if (ignore) return
        if (err.status === 404) setMissing(true)
        else setError(err.message)
      })
      .finally(() => !ignore && setLoading(false))
    return () => {
      ignore = true
    }
  }, [token])

  if (loading) return <Spinner className="py-20" />
  if (missing) {
    return (
      <div className="max-w-lg mx-auto text-center py-16">
        <h1 className="text-2xl font-display text-secondary mb-2">This listing isn&apos;t available</h1>
        <p className="text-text-muted mb-8">
          The link may be old, or the item is no longer for sale. Ask the person who shared it for a new one.
        </p>
        <Link to="/store" className="text-primary hover:underline">Browse the store</Link>
      </div>
    )
  }
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  const { product: p, storefront, shipping_rules: rules = DEFAULT_SHIPPING_RULES } = data
  const max = maxQuantity(p)
  const soldOut = p.stock_quantity === 0
  const limitReached = !soldOut && p.remaining_this_month === 0
  const count = Math.max(1, Math.min(qty, max || 1))
  const shipping = cartShipping([{ product: p, quantity: count }], rules)
  const notTakingOrders = storefront.accepts_payments === false

  const buy = () => {
    if (!user) {
      setShowLoginPrompt(true)
      return
    }
    navigate(`/store/checkout?private=${encodeURIComponent(token)}&qty=${count}`)
  }

  const stepCls = 'w-11 h-11 flex items-center justify-center bg-bg-elevated hover:bg-bg-raised text-text-muted hover:text-text transition-colors disabled:opacity-30 disabled:hover:bg-bg-elevated'

  return (
    <div className="max-w-xl mx-auto">
      <p className="text-xs uppercase tracking-wide text-text-muted mb-2">{storefront.name}</p>
      <div className="bg-bg-surface border border-border rounded-lg overflow-hidden">
        <ProductGallery product={p} />
        <div className="p-5">
          <h1 className="text-2xl font-display text-secondary">{p.name}</h1>
          <p className="text-xl font-semibold text-text-primary mt-1">{formatMoney(p.price_cents, p.currency)}</p>
          {p.description && (
            <p className="text-sm text-text-muted mt-3 whitespace-pre-line">{p.description}</p>
          )}

          {soldOut ? (
            <p className="mt-5 text-sm font-medium bg-accent-red/15 text-accent-red rounded-lg px-4 py-3">Sold out</p>
          ) : limitReached ? (
            <p className="mt-5 text-sm bg-bg-elevated text-text-muted rounded-lg px-4 py-3">
              You&apos;ve reached the monthly limit for this item.
            </p>
          ) : (
            <>
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <div className="flex items-center rounded-lg border border-border overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setQty(count - 1)}
                    disabled={count <= 1}
                    className={stepCls}
                    aria-label="One less"
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 7h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                  </button>
                  <span className="w-11 h-11 flex items-center justify-center text-sm font-medium bg-bg-surface border-x border-border" aria-live="polite">
                    {count}
                  </span>
                  <button
                    type="button"
                    onClick={() => setQty(count + 1)}
                    disabled={count >= max}
                    className={stepCls}
                    aria-label="One more"
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14"><path d="M7 3v8M3 7h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                  </button>
                </div>
                <button
                  type="button"
                  onClick={buy}
                  disabled={notTakingOrders}
                  className="flex-1 min-w-40 bg-primary hover:bg-primary-dark text-white font-semibold px-5 py-3 rounded-lg transition-colors disabled:opacity-50"
                >
                  {notTakingOrders ? 'Not taking orders yet' : user ? `Buy now · ${formatMoney(p.price_cents * count, p.currency)}` : 'Log in to buy'}
                </button>
              </div>
              <div className="mt-3 text-xs text-text-muted space-y-1">
                {shipping && <p>{shippingLabel(shipping, rules)}: {formatMoney(shipping.cents)}</p>}
                {p.max_per_user_monthly != null && (
                  <p>
                    Limit {p.max_per_user_monthly} per month
                    {p.remaining_this_month != null && p.remaining_this_month < p.max_per_user_monthly &&
                      ` · ${p.remaining_this_month} left for you`}
                  </p>
                )}
                {p.stock_quantity <= 5 && (
                  <p className="text-yellow-500 font-medium">Only {p.stock_quantity} left</p>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-secondary/50 bg-secondary/10 px-4 py-3">
        <p className="text-sm font-semibold text-secondary">US shipping only. We can&apos;t ship outside the United States.</p>
        {storefront.shipping_note && (
          <p className="mt-1.5 text-sm text-text-muted whitespace-pre-line">{storefront.shipping_note}</p>
        )}
      </div>

      {showLoginPrompt && <LoginPromptModal onClose={() => setShowLoginPrompt(false)} />}
    </div>
  )
}
