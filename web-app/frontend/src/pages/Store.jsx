import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { getProducts, getStorefronts, formatMoney } from '@/api/store'
import useStoreCart, {
  DEFAULT_STOREFRONT, cartCount, maxQuantity, reconcileCart,
} from '@/hooks/useStoreCart'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

function LoginPromptModal({ onClose }) {
  const returnUrl = encodeURIComponent(window.location.href)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="p-6 text-center">
          <h3 className="text-lg font-display text-secondary mb-2">Sign in to check out</h3>
          <p className="text-sm text-text-muted mb-5">
            Your cart is saved and will be waiting when you get back.
          </p>
          <div className="space-y-3 mb-4">
            <a
              href={`/auth/discord?next=${returnUrl}`}
              className="block w-full px-5 py-3 bg-[#5865F2] text-white rounded-lg font-medium hover:bg-[#4752C4] transition-colors"
            >
              Sign in with Discord
            </a>
            <a
              href={`/auth/google?next=${returnUrl}`}
              className="block w-full px-5 py-3 bg-bg-elevated border border-border rounded-lg font-medium hover:border-primary/50 transition-colors"
            >
              Sign in with Google
            </a>
          </div>
          <button
            onClick={onClose}
            className="text-sm text-text-muted hover:text-text transition-colors"
          >
            Keep browsing
          </button>
        </div>
      </div>
    </div>
  )
}

function productImages(p) {
  if (p.images?.length) return p.images
  return p.image_url ? [p.image_url] : []
}

// Main image plus a thumbnail strip when a product has more than one image.
function ProductGallery({ product }) {
  const images = productImages(product)
  const [index, setIndex] = useState(0)
  const current = images[Math.min(index, images.length - 1)]

  if (images.length === 0) {
    return (
      <div className="w-full h-48 bg-gradient-to-br from-bg-elevated to-bg-surface flex items-center justify-center">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" className="text-border">
          <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" />
          <path d="M21 15l-5-5L5 21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    )
  }

  return (
    <div>
      <img src={current} alt={product.name} className="w-full h-48 object-cover" />
      {images.length > 1 && (
        <div className="flex gap-1.5 p-2 overflow-x-auto bg-bg-elevated/60" role="list" aria-label={`${product.name} images`}>
          {images.map((url, i) => (
            <button
              key={url}
              type="button"
              role="listitem"
              onClick={() => setIndex(i)}
              aria-label={`Show image ${i + 1} of ${product.name}`}
              aria-current={i === index ? 'true' : undefined}
              className={`shrink-0 rounded border overflow-hidden transition-colors ${
                i === index ? 'border-secondary' : 'border-border hover:border-secondary/50'
              }`}
            >
              <img src={url} alt="" className="h-12 w-12 object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Used when the storefront list can't load: everything shows in one tab
const FALLBACK_STOREFRONTS = [{ id: null, slug: DEFAULT_STOREFRONT, name: 'Summit Store' }]

export default function Store() {
  usePageTitle('Store')
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [allProducts, setAllProducts] = useState([])
  const [storefronts, setStorefronts] = useState(FALLBACK_STOREFRONTS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showLoginPrompt, setShowLoginPrompt] = useState(false)

  const active =
    storefronts.find((s) => s.slug === params.get('storefront')) || storefronts[0]
  // Each storefront has its own cart, because each one checks out separately
  const [cart, setCart] = useStoreCart(active.slug) // { [productId]: quantity }
  const products = allProducts.filter((p) =>
    active.id == null || p.storefront_id === active.id ||
    (p.storefront_id == null && active === storefronts[0]),
  )

  useEffect(() => {
    Promise.all([
      getProducts(),
      getStorefronts().catch(() => null),
    ])
      .then(([data, sf]) => {
        setAllProducts(data.products || [])
        if (sf?.storefronts?.length) setStorefronts(sf.storefronts)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  // A saved cart may reference sold-out, hidden, or over-limit items
  useEffect(() => {
    if (!loading) setCart((c) => reconcileCart(c, products))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, active.slug, allProducts])

  const setQty = (id, qty, max) => {
    const clamped = Math.max(0, Math.min(qty, max))
    setCart((c) => {
      const next = { ...c }
      if (clamped === 0) delete next[id]
      else next[id] = clamped
      return next
    })
  }

  const cartItems = products.filter((p) => cart[p.id])
  const subtotal = cartItems.reduce((sum, p) => sum + p.price_cents * cart[p.id], 0)
  const totalQty = cartItems.reduce((n, p) => n + cart[p.id], 0)

  // Storefronts other than Summit can't check out until their Stripe is set up
  const notTakingOrders = active.accepts_payments === false
  const goToCheckout = () =>
    navigate(`/store/checkout?storefront=${encodeURIComponent(active.slug)}`)

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <h1 className="text-2xl font-display text-secondary">Sorcery Community Store</h1>
        <div className="flex flex-col items-end gap-2">
          {user && (
            <Link to="/store/orders" className="text-sm text-primary hover:underline">
              My orders
            </Link>
          )}
          <Link
            to="/store/apply"
            className="text-sm font-medium px-3 py-1.5 rounded-lg border border-brand-line bg-brand-panel text-brand-sky hover:border-primary/60 transition-colors"
          >
            Apply to have a storefront
          </Link>
        </div>
      </div>

      <div role="tablist" aria-label="Storefronts" className="flex gap-6 border-b border-border mb-6 overflow-x-auto">
        {storefronts.map((sf) => {
          const selected = sf.slug === active.slug
          const inCart = selected ? totalQty : cartCount(sf.slug)
          return (
            <button
              key={sf.slug}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setParams(sf === storefronts[0] ? {} : { storefront: sf.slug })}
              className={`py-3 -mb-px border-b-2 text-sm font-semibold whitespace-nowrap transition-colors flex items-center gap-2 ${
                selected
                  ? 'border-secondary text-secondary'
                  : 'border-transparent text-text-muted hover:text-text'
              }`}
            >
              {sf.name}
              {inCart > 0 && (
                <span className="text-xs bg-bg-elevated text-text rounded-full px-2 py-0.5" aria-label={`${inCart} in cart`}>
                  {inCart}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {active.description && (
        <p className="text-sm text-text-muted mb-5 max-w-3xl">{active.description}</p>
      )}

      {notTakingOrders && (
        <p className="text-sm bg-secondary/10 border border-secondary/30 rounded-lg px-4 py-3 mb-5 max-w-3xl">
          {active.name} isn't taking orders yet. You can still browse their products.
        </p>
      )}

      {products.length === 0 ? (
        <p className="text-center text-text-muted py-12">
          Nothing for sale right now. Check back soon!
        </p>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => {
            const qty = cart[p.id] || 0
            const max = maxQuantity(p)
            const soldOut = p.stock_quantity === 0
            const limitReached = !soldOut && p.remaining_this_month === 0
            const lowStock = !soldOut && p.stock_quantity <= 5
            return (
              <div
                key={p.id}
                className={`bg-bg-surface border rounded-lg overflow-hidden flex flex-col transition-all duration-200 ${
                  soldOut
                    ? 'border-border opacity-60'
                    : 'border-border hover:border-secondary/40 hover:-translate-y-0.5 hover:shadow-harsh'
                }`}
              >
                <ProductGallery product={p} />
                <div className="p-4 flex flex-col flex-1">
                  <h2 className="font-semibold text-text-primary">{p.name}</h2>
                  {p.description && (
                    <p className="text-sm text-text-muted mt-1 flex-1">{p.description}</p>
                  )}
                  <div className="flex items-center justify-between mt-3">
                    <span className="text-secondary font-semibold text-lg">
                      {formatMoney(p.price_cents, p.currency)}
                    </span>
                    {soldOut ? (
                      <span className="text-xs font-medium bg-accent-red/20 text-accent-red px-2.5 py-1 rounded-full">
                        Sold out
                      </span>
                    ) : limitReached ? (
                      <span className="text-xs font-medium bg-bg-elevated text-text-muted px-2.5 py-1 rounded-full">
                        Monthly limit reached
                      </span>
                    ) : (
                      <div className="flex items-center rounded-lg border border-border overflow-hidden">
                        <button
                          onClick={() => setQty(p.id, qty - 1, max)}
                          disabled={qty === 0}
                          className="w-9 h-9 flex items-center justify-center bg-bg-elevated hover:bg-bg-raised text-text-muted hover:text-text transition-colors disabled:opacity-30 disabled:hover:bg-bg-elevated"
                          aria-label={`Remove one ${p.name}`}
                        >
                          <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 7h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                        </button>
                        <span className="w-9 h-9 flex items-center justify-center text-sm font-medium bg-bg-surface border-x border-border">
                          {qty}
                        </span>
                        <button
                          onClick={() => setQty(p.id, qty + 1, max)}
                          disabled={qty >= max}
                          className="w-9 h-9 flex items-center justify-center bg-bg-elevated hover:bg-bg-raised text-text-muted hover:text-text transition-colors disabled:opacity-30 disabled:hover:bg-bg-elevated"
                          aria-label={`Add one ${p.name}`}
                        >
                          <svg width="14" height="14" viewBox="0 0 14 14"><path d="M7 3v8M3 7h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                        </button>
                      </div>
                    )}
                  </div>
                  {p.max_per_user_monthly != null && (
                    <p className="text-xs text-text-muted mt-2">
                      Limit {p.max_per_user_monthly} per month
                      {p.remaining_this_month != null && !limitReached &&
                        p.remaining_this_month < p.max_per_user_monthly &&
                        ` · ${p.remaining_this_month} left for you`}
                    </p>
                  )}
                  {lowStock && (
                    <p className="text-xs text-yellow-500 font-medium mt-2">
                      Only {p.stock_quantity} left
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {cartItems.length > 0 && (
        <div className="sticky bottom-4 mt-8 bg-bg-elevated border border-secondary/30 rounded-lg p-4 flex items-center justify-between shadow-harsh">
          <div className="text-sm">
            {storefronts.length > 1 && (
              <span className="block text-xs text-text-muted mb-0.5">{active.name} cart</span>
            )}
            <span className="font-medium text-text-primary">
              {totalQty} {totalQty === 1 ? 'item' : 'items'}
            </span>
            {' '}&middot;{' '}
            <span className="text-secondary font-semibold">{formatMoney(subtotal)}</span>
            <span className="text-text-muted ml-1.5 hidden sm:inline">+ shipping at checkout</span>
          </div>
          {notTakingOrders ? (
            <button
              disabled
              className="bg-primary text-white font-medium px-5 py-2.5 rounded-lg opacity-50"
            >
              Not taking orders yet
            </button>
          ) : user ? (
            <button
              onClick={goToCheckout}
              className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors flex items-center gap-2"
            >
              Checkout
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          ) : (
            <button
              onClick={() => setShowLoginPrompt(true)}
              className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors"
            >
              Log in to check out
            </button>
          )}
        </div>
      )}

      {showLoginPrompt && <LoginPromptModal onClose={() => setShowLoginPrompt(false)} />}
    </div>
  )
}
