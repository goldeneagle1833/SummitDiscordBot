import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getMyOrders, adminGetUserOrders, formatMoney } from '@/api/store'

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
  paid: 'Paid',
  shipped: 'Shipped',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  refunded: 'Refunded',
}

export default function PlayerOrders({ playerId, isOwner, isAdmin }) {
  const [orders, setOrders] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    const fetch = isOwner
      ? getMyOrders()
      : adminGetUserOrders(playerId)
    fetch
      .then((d) => setOrders(d.orders || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [open, playerId, isOwner])

  return (
    <div className="bg-bg-surface border border-border rounded-lg">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <h2 className="font-semibold text-text-primary">
          {isOwner ? 'My Orders' : 'Orders'}
        </h2>
        <span className="text-text-muted text-sm">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3">
          {loading ? (
            <p className="text-text-muted text-sm py-4 text-center">Loading...</p>
          ) : orders.length === 0 ? (
            <p className="text-text-muted text-sm py-4 text-center">No orders yet.</p>
          ) : (
            <div className="space-y-2">
              {orders.map((o) => (
                <div key={o.order_number} className="flex flex-wrap items-center justify-between gap-2 text-sm py-1.5 border-b border-border/50 last:border-0">
                  <span className="font-mono text-xs">{o.order_number}</span>
                  <span className={STATUS_STYLES[o.status] || ''}>{STATUS_LABELS[o.status] || o.status}</span>
                  <span className="text-secondary font-medium">{formatMoney(o.total_cents, o.currency)}</span>
                  <span className="text-text-muted text-xs">{new Date(o.created_at).toLocaleDateString()}</span>
                </div>
              ))}
            </div>
          )}
          {isOwner && (
            <Link to="/store/orders" className="block text-center text-sm text-primary hover:underline mt-3">
              View all orders
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
