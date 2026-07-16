import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { getProducts, formatMoney } from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Store() {
  usePageTitle('Store')
  const { user } = useAuth()
  const navigate = useNavigate()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [cart, setCart] = useState({}) // { [productId]: quantity }

  useEffect(() => {
    getProducts()
      .then((data) => setProducts(data.products || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

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

  const goToCheckout = () => {
    navigate('/store/checkout', {
      state: {
        items: cartItems.map((p) => ({
          product_id: p.id,
          quantity: cart[p.id],
          name: p.name,
          price_cents: p.price_cents,
        })),
      },
    })
  }

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-display text-secondary">Store</h1>
        {user && (
          <Link to="/store/orders" className="text-sm text-primary hover:underline">
            My orders
          </Link>
        )}
      </div>

      {products.length === 0 ? (
        <p className="text-center text-text-muted py-12">
          Nothing for sale right now. Check back soon!
        </p>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => {
            const qty = cart[p.id] || 0
            const soldOut = p.stock_quantity === 0
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
                {p.image_url ? (
                  <img
                    src={p.image_url}
                    alt={p.name}
                    className="w-full h-48 object-cover"
                  />
                ) : (
                  <div className="w-full h-48 bg-gradient-to-br from-bg-elevated to-bg-surface flex items-center justify-center">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" className="text-border">
                      <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.5" />
                      <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" />
                      <path d="M21 15l-5-5L5 21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                )}
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
                    ) : (
                      <div className="flex items-center rounded-lg border border-border overflow-hidden">
                        <button
                          onClick={() => setQty(p.id, qty - 1, p.stock_quantity)}
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
                          onClick={() => setQty(p.id, qty + 1, p.stock_quantity)}
                          disabled={qty >= p.stock_quantity}
                          className="w-9 h-9 flex items-center justify-center bg-bg-elevated hover:bg-bg-raised text-text-muted hover:text-text transition-colors disabled:opacity-30 disabled:hover:bg-bg-elevated"
                          aria-label={`Add one ${p.name}`}
                        >
                          <svg width="14" height="14" viewBox="0 0 14 14"><path d="M7 3v8M3 7h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                        </button>
                      </div>
                    )}
                  </div>
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
            <span className="font-medium text-text-primary">
              {totalQty} {totalQty === 1 ? 'item' : 'items'}
            </span>
            {' '}&middot;{' '}
            <span className="text-secondary font-semibold">{formatMoney(subtotal)}</span>
            <span className="text-text-muted ml-1.5 hidden sm:inline">+ shipping at checkout</span>
          </div>
          {user ? (
            <button
              onClick={goToCheckout}
              className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors flex items-center gap-2"
            >
              Checkout
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          ) : (
            <Link
              to="/login"
              className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2.5 rounded-lg transition-colors"
            >
              Log in to check out
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
