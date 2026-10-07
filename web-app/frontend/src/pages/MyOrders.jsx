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

function OrderCard({ order }) {
  const [expanded, setExpanded] = useState(false)
  const items = order.items || []

  return (
    <div className="bg-bg-surface border border-border rounded-lg overflow-hidden hover:border-border/80 transition-colors">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full p-4 text-left"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm text-text-primary">{order.order_number}</span>
            {order.storefront_name && (
              <span className="text-xs font-medium px-2 py-0.5 rounded-full border border-brand-line bg-brand-panel text-brand-sky">
                {order.storefront_name}
              </span>
            )}
            <span className="text-xs text-text-muted">
              {new Date(order.created_at).toLocaleDateString(undefined, {
                year: 'numeric', month: 'short', day: 'numeric',
              })}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-secondary font-semibold">{formatMoney(order.total_cents, order.currency)}</span>
            <StatusBadge status={order.status} />
            <svg
              width="16" height="16" viewBox="0 0 16 16" fill="none"
              className={`text-text-muted transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
            >
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border">
          {items.length > 0 ? (
            <div className="divide-y divide-border/50">
              {items.map((item, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt={item.product_name}
                      className="w-12 h-12 rounded-md object-cover border border-border shrink-0"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-md bg-bg-elevated border border-border flex items-center justify-center shrink-0">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="text-border">
                        <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.5" />
                        <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" />
                        <path d="M21 15l-5-5L5 21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">{item.product_name}</p>
                    <p className="text-xs text-text-muted">
                      {formatMoney(item.unit_price_cents, order.currency)} x {item.quantity}
                    </p>
                  </div>
                  <span className="text-sm font-medium text-text-primary shrink-0">
                    {formatMoney(item.unit_price_cents * item.quantity, order.currency)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="px-4 py-3 text-sm text-text-muted">No item details available.</p>
          )}

          {order.tracking_number && (
            <div className="border-t border-border/50 px-4 py-3 flex items-center gap-2 text-sm">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-text-muted shrink-0">
                <rect x="1" y="3" width="15" height="13" rx="2" />
                <polygon points="16 8 20 8 23 11 23 16 16 16 16 8" />
                <circle cx="5.5" cy="18.5" r="2.5" />
                <circle cx="18.5" cy="18.5" r="2.5" />
              </svg>
              <span className="text-text-muted">{order.tracking_carrier || 'Tracking'}:</span>
              <span className="font-mono text-text-primary">{order.tracking_number}</span>
            </div>
          )}

          {order.storefront_contact_email && (
            <div className="border-t border-border/50 px-4 py-3 text-sm text-text-muted">
              Questions about this order?{' '}
              <a href={`mailto:${order.storefront_contact_email}`} className="text-primary hover:underline">
                Contact {order.storefront_name}
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const ALL = ''

export default function MyOrders() {
  usePageTitle('My Orders')
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState(ALL)

  useEffect(() => {
    getMyOrders()
      .then((data) => setOrders(data.orders || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  // One section per storefront the buyer has ordered from, in first-seen order
  const sections = []
  for (const o of orders) {
    const slug = o.storefront_slug || 'summit'
    if (!sections.some((s) => s.slug === slug)) {
      sections.push({ slug, name: o.storefront_name || 'Summit Store' })
    }
  }
  const countFor = (slug) =>
    orders.filter((o) => (o.storefront_slug || 'summit') === slug).length
  const shown = tab === ALL
    ? orders
    : orders.filter((o) => (o.storefront_slug || 'summit') === tab)
  const tabs = [{ slug: ALL, name: 'All orders', count: orders.length },
    ...sections.map((s) => ({ ...s, count: countFor(s.slug) }))]

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-4">
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
        <>
          <div role="tablist" aria-label="Orders by storefront" className="flex gap-6 border-b border-border mb-5 overflow-x-auto">
            {tabs.map((t) => (
              <button
                key={t.slug || 'all'}
                type="button"
                role="tab"
                aria-selected={tab === t.slug}
                onClick={() => setTab(t.slug)}
                className={`py-3 -mb-px border-b-2 text-sm font-semibold whitespace-nowrap transition-colors flex items-center gap-2 ${
                  tab === t.slug
                    ? 'border-secondary text-secondary'
                    : 'border-transparent text-text-muted hover:text-text'
                }`}
              >
                {t.name}
                <span className="text-xs bg-bg-elevated text-text-muted rounded-full px-2 py-0.5">{t.count}</span>
              </button>
            ))}
          </div>
          <div className="space-y-3">
            {shown.map((o) => (
              <OrderCard key={o.order_number} order={o} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
