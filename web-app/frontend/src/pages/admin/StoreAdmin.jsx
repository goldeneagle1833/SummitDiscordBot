import { useState, useEffect, useCallback, useRef } from 'react'
import {
  adminGetProducts, adminCreateProduct, adminUpdateProduct, adminDeactivateProduct,
  adminGetOrders, adminGetOrder, adminShipOrder, adminSetOrderStatus, formatMoney,
} from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const inputCls =
  'rounded border border-border bg-bg-surface px-3 py-2 text-sm focus:outline-none focus:border-primary'

// ---------------------------------------------------------------- Products

const EMPTY_PRODUCT = { sku: '', name: '', description: '', price: '', stock_quantity: '', image_url: '', max_per_user_monthly: '' }

function ProductsPanel() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [form, setForm] = useState(EMPTY_PRODUCT)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)

  const uploadImage = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('image', file)
      const r = await fetch('/api/store/admin/products/upload-image', {
        method: 'POST',
        body: fd,
        credentials: 'include',
      })
      const d = await r.json()
      if (d.success) setForm((x) => ({ ...x, image_url: d.url }))
      else setError(`Upload failed: ${d.error}`)
    } catch {
      setError('Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const load = useCallback(() => {
    adminGetProducts()
      .then((d) => setProducts(d.products || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  useEffect(load, [load])

  const set = (f) => (e) => setForm((x) => ({ ...x, [f]: e.target.value }))

  const addProduct = async () => {
    setError(null)
    const price_cents = Math.round(parseFloat(form.price) * 100)
    if (!form.sku.trim() || !form.name.trim() || !Number.isFinite(price_cents)) {
      setError('SKU, name, and a valid price are required')
      return
    }
    setSaving(true)
    try {
      const maxMonthly = form.max_per_user_monthly ? parseInt(form.max_per_user_monthly, 10) : undefined
      await adminCreateProduct({
        sku: form.sku.trim(),
        name: form.name.trim(),
        description: form.description.trim(),
        price_cents,
        stock_quantity: parseInt(form.stock_quantity || '0', 10),
        image_url: form.image_url.trim() || undefined,
        max_per_user_monthly: maxMonthly || undefined,
      })
      setForm(EMPTY_PRODUCT)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const updateStock = async (p, value) => {
    const stock_quantity = parseInt(value, 10)
    if (!Number.isFinite(stock_quantity) || stock_quantity < 0) return
    try {
      await adminUpdateProduct(p.id, { stock_quantity })
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  const toggleActive = async (p) => {
    try {
      if (p.is_active) await adminDeactivateProduct(p.id)
      else await adminUpdateProduct(p.id, { is_active: 1 })
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  if (loading) return <Spinner className="py-12" />

  return (
    <div>
      <div className="bg-bg-surface border border-border rounded-lg p-4 mb-6">
        <h2 className="font-semibold mb-3">Add product</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <input className={inputCls} placeholder="SKU (e.g. TOK-FIRE)" value={form.sku} onChange={set('sku')} />
          <input className={inputCls} placeholder="Name" value={form.name} onChange={set('name')} />
          <input className={`${inputCls} sm:col-span-2`} placeholder="Description" value={form.description} onChange={set('description')} />
          <input className={inputCls} placeholder="Price (e.g. 12.99)" inputMode="decimal" value={form.price} onChange={set('price')} />
          <input className={inputCls} placeholder="Stock quantity" inputMode="numeric" value={form.stock_quantity} onChange={set('stock_quantity')} />
          <input className={inputCls} placeholder="Monthly limit per user (blank = unlimited)" inputMode="numeric" value={form.max_per_user_monthly} onChange={set('max_per_user_monthly')} />
          <div className="sm:col-span-2 flex items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.gif"
              onChange={uploadImage}
              className="hidden"
              id="product-image-file"
            />
            <label
              htmlFor="product-image-file"
              className="cursor-pointer rounded border border-border bg-bg-elevated px-4 py-2 text-sm hover:border-primary transition-colors"
            >
              {uploading ? 'Uploading…' : 'Upload image'}
            </label>
            {form.image_url ? (
              <>
                <img src={form.image_url} alt="Product preview" className="h-12 w-12 object-cover rounded border border-border" />
                <button
                  type="button"
                  onClick={() => setForm((x) => ({ ...x, image_url: '' }))}
                  className="text-sm text-text-muted hover:text-accent-red"
                >
                  Remove
                </button>
              </>
            ) : (
              <input
                className={`${inputCls} flex-1`}
                placeholder="…or paste an image URL"
                value={form.image_url}
                onChange={set('image_url')}
              />
            )}
          </div>
        </div>
        <button
          onClick={addProduct}
          disabled={saving}
          className="mt-3 bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2 rounded transition-colors disabled:opacity-50"
        >
          {saving ? 'Adding…' : 'Add product'}
        </button>
      </div>

      {error && <p className="text-accent-red text-sm mb-3">{error}</p>}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3" />
              <th className="py-2 px-3 font-semibold text-text-muted">SKU</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Name</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Price</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Stock</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Limit/mo</th>
              <th className="py-2 px-3 font-semibold text-text-muted">Status</th>
              <th className="py-2 px-3" />
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id} className="border-b border-border/50 hover:bg-bg-surface/50">
                <td className="py-2 px-3">
                  {p.image_url ? (
                    <img src={p.image_url} alt="" className="h-10 w-10 object-cover rounded border border-border" />
                  ) : (
                    <div className="h-10 w-10 rounded border border-border bg-bg-elevated" />
                  )}
                </td>
                <td className="py-2 px-3 font-mono text-xs">{p.sku}</td>
                <td className="py-2 px-3">{p.name}</td>
                <td className="py-2 px-3 text-secondary">{formatMoney(p.price_cents, p.currency)}</td>
                <td className="py-2 px-3">
                  <input
                    type="number"
                    min="0"
                    defaultValue={p.stock_quantity}
                    onBlur={(e) => e.target.value !== String(p.stock_quantity) && updateStock(p, e.target.value)}
                    className={`${inputCls} w-20 py-1`}
                    aria-label={`Stock for ${p.name}`}
                  />
                </td>
                <td className="py-2 px-3 text-text-muted text-sm">
                  {p.max_per_user_monthly ?? '∞'}
                </td>
                <td className="py-2 px-3">
                  {p.is_active ? (
                    <span className="text-accent-green">Active</span>
                  ) : (
                    <span className="text-text-muted">Hidden</span>
                  )}
                </td>
                <td className="py-2 px-3 text-right">
                  <button onClick={() => toggleActive(p)} className="text-primary hover:underline">
                    {p.is_active ? 'Hide' : 'Show'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {products.length === 0 && (
          <p className="text-center text-text-muted py-8">No products yet. Add your first one above.</p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- Orders

const QUEUE_FILTERS = [
  { key: 'paid', label: 'To ship' },
  { key: 'shipped', label: 'Shipped' },
  { key: 'delivered', label: 'Delivered' },
  { key: 'pending_payment', label: 'Awaiting payment' },
  { key: '', label: 'All' },
]

function OrderRow({ order, onChanged }) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState(null)
  const [tracking, setTracking] = useState('')
  const [carrier, setCarrier] = useState('USPS')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const toggle = async () => {
    if (!expanded && !detail) {
      const d = await adminGetOrder(order.id).catch(() => null)
      setDetail(d?.order || null)
    }
    setExpanded((x) => !x)
  }

  const ship = async () => {
    if (!tracking.trim()) return setError('Tracking number required')
    setBusy(true)
    setError(null)
    try {
      await adminShipOrder(order.id, tracking.trim(), carrier)
      onChanged()
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  const setStatus = async (status) => {
    setBusy(true)
    setError(null)
    try {
      await adminSetOrderStatus(order.id, status)
      onChanged()
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <div className="bg-bg-surface border border-border rounded-lg">
      <button onClick={toggle} className="w-full flex flex-wrap items-center justify-between gap-2 p-3 text-left">
        <span className="font-mono text-sm">{order.order_number}</span>
        <span className="text-sm">{order.username}</span>
        <span className="text-sm text-secondary font-medium">{formatMoney(order.total_cents, order.currency)}</span>
        <span className="text-sm text-text-muted">{order.status}</span>
      </button>

      {expanded && (
        <div className="border-t border-border p-3 text-sm space-y-3">
          {detail ? (
            <>
              <div>
                {detail.items.map((i) => (
                  <div key={i.id}>
                    {i.quantity}x {i.product_name} — {formatMoney(i.unit_price_cents * i.quantity)}
                  </div>
                ))}
              </div>
              <div className="text-text-muted">
                <div>{detail.ship_name}</div>
                <div>{detail.ship_line1}{detail.ship_line2 ? `, ${detail.ship_line2}` : ''}</div>
                <div>{detail.ship_city}, {detail.ship_state} {detail.ship_postal}</div>
                {detail.email && <div>{detail.email}</div>}
              </div>
            </>
          ) : (
            <Spinner className="py-2" />
          )}

          {order.status === 'paid' && (
            <div className="flex flex-wrap items-center gap-2">
              <input className={`${inputCls} flex-1 min-w-40`} placeholder="Tracking number" value={tracking} onChange={(e) => setTracking(e.target.value)} />
              <select className={inputCls} value={carrier} onChange={(e) => setCarrier(e.target.value)}>
                <option>USPS</option>
                <option>UPS</option>
                <option>FedEx</option>
                <option>Other</option>
              </select>
              <button
                onClick={ship}
                disabled={busy}
                className="bg-accent-green hover:opacity-90 text-white font-medium px-4 py-2 rounded disabled:opacity-50"
              >
                Mark shipped
              </button>
            </div>
          )}
          {order.status === 'shipped' && (
            <button onClick={() => setStatus('delivered')} disabled={busy} className="text-primary hover:underline">
              Mark delivered
            </button>
          )}
          {(order.status === 'paid' || order.status === 'pending_payment') && (
            <button onClick={() => setStatus('cancelled')} disabled={busy} className="text-accent-red hover:underline ml-4">
              Cancel order{order.status === 'pending_payment' ? ' (restocks items)' : ''}
            </button>
          )}
          {error && <p className="text-accent-red">{error}</p>}
        </div>
      )}
    </div>
  )
}

function OrdersPanel() {
  const [filter, setFilter] = useState('paid')
  const [productFilter, setProductFilter] = useState('')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [products, setProducts] = useState([])
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    adminGetProducts().then((d) => setProducts(d.products || [])).catch(() => {})
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    adminGetOrders({
      status: filter,
      product_id: productFilter || undefined,
      search: search.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    })
      .then((d) => setOrders(d.orders || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [filter, productFilter, search, dateFrom, dateTo])
  useEffect(load, [load])

  const exportCsv = () => {
    const params = new URLSearchParams()
    if (filter) params.set('status', filter)
    if (productFilter) params.set('product_id', productFilter)
    if (search.trim()) params.set('search', search.trim())
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    const qs = params.toString()
    window.open(`/api/store/admin/orders/export${qs ? `?${qs}` : ''}`, '_blank')
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {QUEUE_FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded text-sm border transition-colors ${
              filter === f.key
                ? 'border-primary text-primary bg-primary/10'
                : 'border-border text-text-muted hover:text-text'
            }`}
          >
            {f.label}
          </button>
        ))}
        <button
          onClick={exportCsv}
          className="ml-auto px-3 py-1.5 rounded text-sm border border-border text-text-muted hover:text-text hover:border-primary transition-colors"
        >
          Export CSV
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <input
          className={`${inputCls} w-48`}
          placeholder="Search user / order #"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className={`${inputCls} w-44`}
          value={productFilter}
          onChange={(e) => setProductFilter(e.target.value)}
        >
          <option value="">All products</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <input
          type="date"
          className={`${inputCls} w-36`}
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          title="From date"
        />
        <input
          type="date"
          className={`${inputCls} w-36`}
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          title="To date"
        />
        {(productFilter || search || dateFrom || dateTo) && (
          <button
            onClick={() => { setProductFilter(''); setSearch(''); setDateFrom(''); setDateTo('') }}
            className="text-xs text-text-muted hover:text-accent-red"
          >
            Clear filters
          </button>
        )}
      </div>

      {error && <p className="text-accent-red text-sm mb-3">{error}</p>}
      {loading ? (
        <Spinner className="py-12" />
      ) : orders.length === 0 ? (
        <p className="text-center text-text-muted py-12">No orders here.</p>
      ) : (
        <div className="space-y-2">
          {orders.map((o) => (
            <OrderRow key={o.id} order={o} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- Page

export default function StoreAdmin() {
  usePageTitle('Store Admin')
  const [tab, setTab] = useState('orders')

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-display text-secondary">Store Admin</h1>
        <a
          href="/api/store/admin/backup"
          className="text-sm text-primary hover:underline"
          download
        >
          Download backup
        </a>
      </div>

      <div className="flex gap-2 border-b border-border mb-6">
        {[
          { key: 'orders', label: 'Order queue' },
          { key: 'products', label: 'Products' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key
                ? 'border-secondary text-secondary'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'orders' ? <OrdersPanel /> : <ProductsPanel />}
    </div>
  )
}
