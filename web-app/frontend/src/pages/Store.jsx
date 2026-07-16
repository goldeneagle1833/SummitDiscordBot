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
      <div className="flex items-center justify-between mb-4">
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => {
            const qty = cart[p.id] || 0
            const soldOut = p.stock_quantity === 0
            return (
              <div
                key={p.id}
                className="bg-bg-surface border border-border rounded-lg p-4 flex flex-col"
              >
                {p.image_url && (
                  <img
                    src={p.image_url}
                    alt={p.name}
                    className="w-full h-40 object-cover rounded mb-3"
                  />
                )}
                <h2 className="font-semibold">{p.name}</h2>
                {p.description && (
                  <p className="text-sm text-text-muted mt-1 flex-1">{p.description}</p>
                )}
                <div className="flex items-center justify-between mt-3">
                  <span className="text-secondary font-medium">
                    {formatMoney(p.price_cents, p.currency)}
                  </span>
                  {soldOut ? (
                    <span className="text-sm text-text-muted">Sold out</span>
                  ) : (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setQty(p.id, qty - 1, p.stock_quantity)}
                        disabled={qty === 0}
                        className="w-8 h-8 rounded bg-bg-elevated border border-border disabled:opacity-40"
                        aria-label={`Remove one ${p.name}`}
                      >
                        −
                      </button>
                      <span className="w-6 text-center">{qty}</span>
                      <button
                        onClick={() => setQty(p.id, qty + 1, p.stock_quantity)}
                        disabled={qty >= p.stock_quantity}
                        className="w-8 h-8 rounded bg-bg-elevated border border-border disabled:opacity-40"
                        aria-label={`Add one ${p.name}`}
                      >
                        +
                      </button>
                    </div>
                  )}
                </div>
                {!soldOut && p.stock_quantity <= 5 && (
                  <p className="text-xs text-text-muted mt-2">
                    Only {p.stock_quantity} left
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}

      {cartItems.length > 0 && (
        <div className="sticky bottom-4 mt-6 bg-bg-elevated border border-border rounded-lg p-4 flex items-center justify-between shadow-lg">
          <div className="text-sm">
            {cartItems.reduce((n, p) => n + cart[p.id], 0)} item(s) —{' '}
            <span className="text-secondary font-medium">{formatMoney(subtotal)}</span>
            <span className="text-text-muted"> + shipping (free for supporters!)</span>
          </div>
          {user ? (
            <button
              onClick={goToCheckout}
              className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2 rounded transition-colors"
            >
              Continue to shipping
            </button>
          ) : (
            <Link
              to="/login"
              className="bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2 rounded transition-colors"
            >
              Log in to check out
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
