import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getMyOrders, formatMoney } from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const STATUS_STYLES = {
  pending_payment: 'text-text-muted',
  paid: 'text-primary',
  shipped: 'text-secondary',
  delivered: 'text-accent-green',
  cancelled: 'text-text-muted line-through',
  refunded: 'text-accent-red',
}

const STATUS_LABELS = {
  pending_payment: 'Awaiting payment',
  paid: 'Paid — preparing shipment',
  shipped: 'Shipped',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  refunded: 'Refunded',
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
      <h1 className="text-2xl font-display text-secondary mb-4">My Orders</h1>
      {orders.length === 0 ? (
        <p className="text-center text-text-muted py-12">
          No orders yet. <Link to="/store" className="text-primary hover:underline">Visit the store</Link>
        </p>
      ) : (
        <div className="space-y-3">
          {orders.map((o) => (
            <div key={o.order_number} className="bg-bg-surface border border-border rounded-lg p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-sm">{o.order_number}</span>
                <span className={`text-sm font-medium ${STATUS_STYLES[o.status] || ''}`}>
                  {STATUS_LABELS[o.status] || o.status}
                </span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 mt-2 text-sm text-text-muted">
                <span>{new Date(o.created_at).toLocaleDateString()}</span>
                <span className="text-secondary font-medium">{formatMoney(o.total_cents, o.currency)}</span>
              </div>
              {o.tracking_number && (
                <p className="text-sm mt-2">
                  {o.tracking_carrier || 'Tracking'}:{' '}
                  <span className="font-mono">{o.tracking_number}</span>
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
