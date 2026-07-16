import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getMyOrders, formatMoney } from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const STATUS_CONFIG = {
  pending_payment: { label: 'Awaiting payment', bg: 'bg-text-muted/15', text: 'text-text-muted' },
  paid:            { label: 'Paid \u2014 preparing shipment', bg: 'bg-primary/15', text: 'text-primary' },
  shipped:         { label: 'Shipped', bg: 'bg-secondary/15', text: 'text-secondary' },
  delivered:       { label: 'Delivered', bg: 'bg-accent-green/15', text: 'text-accent-green' },
  cancelled:       { label: 'Cancelled', bg: 'bg-text-muted/10', text: 'text-text-muted line-through' },
  refunded:        { label: 'Refunded', bg: 'bg-accent-red/15', text: 'text-accent-red' },
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, bg: 'bg-bg-elevated', text: 'text-text-muted' }
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  )
}

export default function MyOrders() {
  usePageTitle('My Orders')
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getMyOrders()
      .then((data) => setOrders(data.orders || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-display text-secondary">My Orders</h1>
        <Link to="/store" className="text-sm text-text-muted hover:text-text transition-colors">
          &larr; Back to store
        </Link>
      </div>

      {orders.length === 0 ? (
        <div className="text-center py-16 bg-bg-surface border border-border rounded-lg">
          <p className="text-text-muted mb-3">No orders yet.</p>
          <Link to="/store" className="text-primary hover:underline text-sm font-medium">
            Visit the store
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {orders.map((o) => (
            <div key={o.order_number} className="bg-bg-surface border border-border rounded-lg p-4 hover:border-border/80 transition-colors">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm text-text-primary">{o.order_number}</span>
                  <span className="text-xs text-text-muted">
                    {new Date(o.created_at).toLocaleDateString(undefined, {
                      year: 'numeric', month: 'short', day: 'numeric',
                    })}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-secondary font-semibold">{formatMoney(o.total_cents, o.currency)}</span>
                  <StatusBadge status={o.status} />
                </div>
              </div>
              {o.tracking_number && (
                <div className="mt-3 pt-3 border-t border-border/50 flex items-center gap-2 text-sm">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-text-muted shrink-0">
                    <rect x="1" y="3" width="15" height="13" rx="2" />
                    <polygon points="16 8 20 8 23 11 23 16 16 16 16 8" />
                    <circle cx="5.5" cy="18.5" r="2.5" />
                    <circle cx="18.5" cy="18.5" r="2.5" />
                  </svg>
                  <span className="text-text-muted">{o.tracking_carrier || 'Tracking'}:</span>
                  <span className="font-mono text-text-primary">{o.tracking_number}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
