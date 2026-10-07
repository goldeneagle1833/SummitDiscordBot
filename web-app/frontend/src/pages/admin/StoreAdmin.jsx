import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  adminGetMe, adminGetProducts, adminCreateProduct, adminUpdateProduct, adminDeactivateProduct,
  adminUploadProductImages,
  adminGetOrders, adminGetOrder, adminShipOrder, adminSetOrderStatus, formatMoney,
  adminCreateStorefront, adminUpdateStorefront,
  adminGetStorefrontAdmins, adminAddStorefrontAdmin, adminRemoveStorefrontAdmin, adminSearchUsers,
  adminGetStorefrontApplications, adminApproveStorefrontApplication,
  adminDeclineStorefrontApplication,
  adminGetStorefrontPayments, adminStartStripeOnboarding, adminDisconnectStripe,
} from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const inputCls =
  'rounded border border-border bg-bg-surface px-3 py-2 text-sm focus:outline-none focus:border-primary'

// ---------------------------------------------------------------- Products

const EMPTY_PRODUCT = {
  sku: '', name: '', description: '', price: '', stock_quantity: '', max_per_user_monthly: '', images: [],
}

function productToForm(p) {
  return {
    sku: p.sku || '',
    name: p.name || '',
    description: p.description || '',
    price: (p.price_cents / 100).toFixed(2),
    stock_quantity: String(p.stock_quantity ?? ''),
    max_per_user_monthly: p.max_per_user_monthly == null ? '' : String(p.max_per_user_monthly),
    images: p.images?.length ? [...p.images] : p.image_url ? [p.image_url] : [],
  }
}

// Shared by "Add product" and the inline editor. `initial` is a product row
// when editing, null when adding.
function ProductForm({ initial, onSaved, onCancel, storefronts = [], defaultStorefrontId = null }) {
  const editing = Boolean(initial)
  const [storefrontId, setStorefrontId] = useState(defaultStorefrontId ?? storefronts[0]?.id ?? '')
  const [form, setForm] = useState(() => (initial ? productToForm(initial) : EMPTY_PRODUCT))
  const [urlDraft, setUrlDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const fileRef = useRef(null)
  const fileInputId = editing ? `product-image-file-${initial.id}` : 'product-image-file'

  const set = (f) => (e) => setForm((x) => ({ ...x, [f]: e.target.value }))
  const setImages = (fn) => setForm((x) => ({ ...x, images: fn(x.images) }))

  const uploadImages = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      const { urls } = await adminUploadProductImages(files)
      setImages((imgs) => [...imgs, ...urls.filter((u) => !imgs.includes(u))])
    } catch (err) {
      setError(`Upload failed: ${err.message}`)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const addUrl = () => {
    const url = urlDraft.trim()
    if (!url) return
    setImages((imgs) => (imgs.includes(url) ? imgs : [...imgs, url]))
    setUrlDraft('')
  }

  const removeImage = (i) => setImages((imgs) => imgs.filter((_, idx) => idx !== i))
  const moveImage = (i, dir) =>
    setImages((imgs) => {
      const j = i + dir
      if (j < 0 || j >= imgs.length) return imgs
      const next = [...imgs]
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  const makePrimary = (i) => setImages((imgs) => [imgs[i], ...imgs.filter((_, idx) => idx !== i)])

  const submit = async () => {
    setError(null)
    const price_cents = Math.round(parseFloat(form.price) * 100)
    if (!form.sku.trim() || !form.name.trim() || !Number.isFinite(price_cents) || price_cents < 0) {
      setError('SKU, name, and a valid price are required')
      return
    }
    const stock_quantity = parseInt(form.stock_quantity || '0', 10)
    if (!Number.isFinite(stock_quantity) || stock_quantity < 0) {
      setError('Stock must be zero or more')
      return
    }
    const maxMonthly = form.max_per_user_monthly.trim() ? parseInt(form.max_per_user_monthly, 10) : null
    if (maxMonthly !== null && (!Number.isFinite(maxMonthly) || maxMonthly < 1)) {
      setError('Monthly limit must be a positive number, or blank for no limit')
      return
    }
    const payload = {
      sku: form.sku.trim(),
      name: form.name.trim(),
      description: form.description.trim(),
      price_cents,
      stock_quantity,
      max_per_user_monthly: maxMonthly,
      images: form.images,
    }
    setSaving(true)
    try {
      if (editing) {
        await adminUpdateProduct(initial.id, payload)
      } else {
        await adminCreateProduct({
          ...payload,
          max_per_user_monthly: maxMonthly ?? undefined,
          storefront_id: storefrontId || undefined,
        })
        setForm(EMPTY_PRODUCT)
      }
      onSaved()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold">{editing ? `Edit ${initial.name}` : 'Add product'}</h2>
        {editing && (
          <button type="button" onClick={onCancel} className="text-sm text-text-muted hover:text-text">
            Cancel
          </button>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {!editing && storefronts.length > 1 && defaultStorefrontId == null && (
          <select
            className={`${inputCls} sm:col-span-2`}
            aria-label="Storefront"
            value={storefrontId}
            onChange={(e) => setStorefrontId(Number(e.target.value))}
          >
            {storefronts.map((sf) => (
              <option key={sf.id} value={sf.id}>{sf.name}</option>
            ))}
          </select>
        )}
        <input className={inputCls} placeholder="SKU (e.g. TOK-FIRE)" aria-label="SKU" value={form.sku} onChange={set('sku')} />
        <input className={inputCls} placeholder="Name" aria-label="Name" value={form.name} onChange={set('name')} />
        <textarea
          className={`${inputCls} sm:col-span-2 min-h-20`}
          placeholder="Description"
          aria-label="Description"
          value={form.description}
          onChange={set('description')}
        />
        <input className={inputCls} placeholder="Price (e.g. 12.99)" aria-label="Price" inputMode="decimal" value={form.price} onChange={set('price')} />
        <input className={inputCls} placeholder="Stock quantity" aria-label="Stock quantity" inputMode="numeric" value={form.stock_quantity} onChange={set('stock_quantity')} />
        <input
          className={inputCls}
          placeholder="Monthly limit per user (blank = unlimited)"
          aria-label="Monthly limit per user"
          inputMode="numeric"
          value={form.max_per_user_monthly}
          onChange={set('max_per_user_monthly')}
        />

        <div className="sm:col-span-2 space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".jpg,.jpeg,.png,.webp,.gif"
              onChange={uploadImages}
              className="hidden"
              id={fileInputId}
            />
            <label
              htmlFor={fileInputId}
              className="cursor-pointer rounded border border-border bg-bg-elevated px-4 py-2 text-sm hover:border-primary transition-colors"
            >
              {uploading ? 'Uploading…' : 'Upload images'}
            </label>
            <input
              className={`${inputCls} flex-1 min-w-48`}
              placeholder="…or paste an image URL"
              aria-label="Image URL"
              value={urlDraft}
              onChange={(e) => setUrlDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addUrl()
                }
              }}
            />
            <button
              type="button"
              onClick={addUrl}
              disabled={!urlDraft.trim()}
              className="text-sm text-primary hover:underline disabled:opacity-40 disabled:no-underline"
            >
              Add URL
            </button>
          </div>

          {form.images.length > 0 ? (
            <ul className="flex flex-wrap gap-3" aria-label="Product images">
              {form.images.map((url, i) => (
                <li key={url} className="relative w-24">
                  <img
                    src={url}
                    alt={i === 0 ? 'Primary image' : `Image ${i + 1}`}
                    className={`h-24 w-24 object-cover rounded border ${i === 0 ? 'border-secondary' : 'border-border'}`}
                  />
                  {i === 0 && (
                    <span className="absolute top-1 left-1 text-[10px] font-medium bg-secondary text-black px-1.5 py-0.5 rounded">
                      Primary
                    </span>
                  )}
                  <div className="mt-1 flex items-center justify-between text-xs text-text-muted">
                    <button type="button" onClick={() => moveImage(i, -1)} disabled={i === 0} aria-label={`Move image ${i + 1} left`} className="hover:text-text disabled:opacity-30">
                      ←
                    </button>
                    {i !== 0 && (
                      <button type="button" onClick={() => makePrimary(i)} className="hover:text-text">
                        Primary
                      </button>
                    )}
                    <button type="button" onClick={() => removeImage(i)} aria-label={`Remove image ${i + 1}`} className="hover:text-accent-red">
                      ✕
                    </button>
                    <button type="button" onClick={() => moveImage(i, 1)} disabled={i === form.images.length - 1} aria-label={`Move image ${i + 1} right`} className="hover:text-text disabled:opacity-30">
                      →
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-text-muted">No images yet. The first image is the one shown in listings.</p>
          )}
        </div>
      </div>

      {error && <p className="text-accent-red text-sm mt-3">{error}</p>}

      <button
        onClick={submit}
        disabled={saving || uploading}
        className="mt-3 bg-primary hover:bg-primary-dark text-white font-medium px-5 py-2 rounded transition-colors disabled:opacity-50"
      >
        {saving ? 'Saving…' : editing ? 'Save changes' : 'Add product'}
      </button>
    </div>
  )
}

function ProductsPanel({ storefrontId, storefronts }) {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null) // product row being edited

  const load = useCallback(() => {
    adminGetProducts(storefrontId)
      .then((d) => setProducts(d.products || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [storefrontId])
  useEffect(load, [load])
  const storefrontName = (id) => storefronts.find((sf) => sf.id === id)?.name

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
      {editing ? (
        <ProductForm
          key={editing.id}
          initial={editing}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      ) : (
        <ProductForm
          key={`new-${storefrontId}`}
          initial={null}
          onSaved={load}
          storefronts={storefronts}
          defaultStorefrontId={storefrontId}
        />
      )}

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
            {products.map((p) => {
              const imageCount = p.images?.length ?? (p.image_url ? 1 : 0)
              return (
                <tr key={p.id} className={`border-b border-border/50 hover:bg-bg-surface/50 ${editing?.id === p.id ? 'bg-primary/5' : ''}`}>
                  <td className="py-2 px-3">
                    <div className="relative h-10 w-10">
                      {p.image_url ? (
                        <img src={p.image_url} alt="" className="h-10 w-10 object-cover rounded border border-border" />
                      ) : (
                        <div className="h-10 w-10 rounded border border-border bg-bg-elevated" />
                      )}
                      {imageCount > 1 && (
                        <span
                          className="absolute -bottom-1 -right-1 text-[10px] font-medium bg-bg-elevated border border-border rounded px-1"
                          title={`${imageCount} images`}
                        >
                          +{imageCount - 1}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2 px-3 font-mono text-xs">{p.sku}</td>
                  <td className="py-2 px-3">
                    {p.name}
                    {storefrontId == null && storefronts.length > 1 && (
                      <span className="block text-xs text-text-muted">{storefrontName(p.storefront_id)}</span>
                    )}
                  </td>
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
                  <td className="py-2 px-3 text-right whitespace-nowrap">
                    <button
                      onClick={() => {
                        setEditing(p)
                        window.scrollTo?.({ top: 0, behavior: 'smooth' })
                      }}
                      className="text-primary hover:underline mr-3"
                      aria-label={`Edit ${p.name}`}
                    >
                      Edit
                    </button>
                    <button onClick={() => toggleActive(p)} className="text-primary hover:underline">
                      {p.is_active ? 'Hide' : 'Show'}
                    </button>
                  </td>
                </tr>
              )
            })}
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

// Keep in sync with TRACKING_REQUIRED_OVER_CENTS in routes/api/store.py
const TRACKING_REQUIRED_OVER_CENTS = 5000

function OrderRow({ order, onChanged, showStorefront = false }) {
  const trackingRequired = order.total_cents > TRACKING_REQUIRED_OVER_CENTS
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
    setBusy(true)
    setError(null)
    try {
      await adminShipOrder(order.id, tracking.trim() || null, tracking.trim() ? carrier : null)
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
      <div className="flex items-center">
        <button onClick={toggle} className="flex-1 flex flex-wrap items-center justify-between gap-2 p-3 text-left">
          <span className="font-mono text-sm">{order.order_number}</span>
          <span className="text-sm">{order.username}</span>
          {showStorefront && order.storefront_name && (
            <span className="text-xs text-brand-sky">{order.storefront_name}</span>
          )}
          <span className="text-sm text-secondary font-medium">{formatMoney(order.total_cents, order.currency)}</span>
          <span className="text-sm text-text-muted">{order.status}</span>
        </button>
        <a
          href={`/admin/store/orders/${order.id}/print?print=1`}
          target="_blank"
          rel="noopener"
          className="shrink-0 mr-3 inline-flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-xs text-text-muted hover:text-text hover:border-primary transition-colors"
          aria-label={`Print order form for ${order.order_number}`}
          title="Open a printable order form in a new tab"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M6 9V3h12v6M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2" />
            <rect x="6" y="14" width="12" height="7" />
          </svg>
          Print
        </a>
      </div>

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
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  className={`${inputCls} flex-1 min-w-40`}
                  placeholder={trackingRequired ? 'Tracking number (required)' : 'Tracking number (optional)'}
                  value={tracking}
                  onChange={(e) => setTracking(e.target.value)}
                />
                {tracking.trim() && (
                  <select className={inputCls} value={carrier} onChange={(e) => setCarrier(e.target.value)}>
                    <option>USPS</option>
                    <option>UPS</option>
                    <option>FedEx</option>
                    <option>Other</option>
                  </select>
                )}
                <button
                  onClick={ship}
                  disabled={busy || (trackingRequired && !tracking.trim())}
                  className="bg-accent-green hover:opacity-90 text-white font-medium px-4 py-2 rounded disabled:opacity-50"
                >
                  Mark shipped
                </button>
              </div>
              {!tracking.trim() && (
                <p className="text-xs text-text-muted mt-1">
                  {trackingRequired
                    ? 'This order is over $50, so it needs a tracking number.'
                    : 'Tracking is only required for orders over $50.'}
                </p>
              )}
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

function OrdersPanel({ storefrontId, showStorefront }) {
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
    adminGetProducts(storefrontId).then((d) => setProducts(d.products || [])).catch(() => {})
  }, [storefrontId])

  const load = useCallback(() => {
    setLoading(true)
    adminGetOrders({
      storefront_id: storefrontId || undefined,
      status: filter,
      product_id: productFilter || undefined,
      search: search.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    })
      .then((d) => setOrders(d.orders || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [storefrontId, filter, productFilter, search, dateFrom, dateTo])
  useEffect(load, [load])

  const exportCsv = () => {
    const params = new URLSearchParams()
    if (storefrontId) params.set('storefront_id', storefrontId)
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
            <OrderRow key={o.id} order={o} onChanged={load} showStorefront={showStorefront} />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- Team

const ROLE_LABELS = {
  manager: 'Manager: products and orders',
  fulfillment: 'Shipper: orders only',
}

function TeamPanel({ storefront }) {
  const [admins, setAdmins] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [picked, setPicked] = useState(null) // { user_id, display_name }
  const [role, setRole] = useState('manager')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    adminGetStorefrontAdmins(storefront.id)
      .then((d) => setAdmins(d.admins || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [storefront.id])
  useEffect(load, [load])

  useEffect(() => {
    if (picked || query.trim().length < 2 || /^\d+$/.test(query.trim())) {
      setResults([])
      return undefined
    }
    const t = setTimeout(() => {
      adminSearchUsers(query.trim()).then((d) => setResults(d.users || [])).catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(t)
  }, [query, picked])

  const typedId = /^\d{5,}$/.test(query.trim()) ? query.trim() : null
  const target = picked || (typedId ? { user_id: typedId, display_name: '' } : null)

  const add = async () => {
    if (!target) return
    setBusy(true)
    setError(null)
    try {
      await adminAddStorefrontAdmin(storefront.id, {
        user_id: target.user_id, username: target.display_name || undefined, role,
      })
      setPicked(null)
      setQuery('')
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (a) => {
    setError(null)
    try {
      await adminRemoveStorefrontAdmin(storefront.id, a.user_id)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="flex flex-wrap gap-6 items-start">
      <div className="flex-[999_1_480px] min-w-0">
        <h2 className="font-semibold text-lg">{storefront.name} admins</h2>
        <p className="text-sm text-text-muted mb-4">
          They only see and manage {storefront.name} orders{' '}
          and products. Full store admins aren&apos;t listed here; they see every storefront.
        </p>
        {loading ? (
          <Spinner className="py-8" />
        ) : admins.length === 0 ? (
          <p className="text-sm text-text-muted py-6 text-center bg-bg-surface border border-border rounded-lg">
            No storefront admins yet.
          </p>
        ) : (
          <ul className="bg-bg-surface border border-border rounded-lg divide-y divide-border">
            {admins.map((a) => (
              <li key={a.user_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{a.username}</div>
                  <div className="text-xs text-text-muted">
                    {ROLE_LABELS[a.role] || a.role}
                    {a.added_by ? ` · added by ${a.added_by}` : ''}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => remove(a)}
                  className="text-sm text-accent-red hover:underline"
                  aria-label={`Remove ${a.username}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex-[1_1_300px] min-w-0 bg-bg-surface border border-border rounded-lg p-4 space-y-3">
        <h3 className="font-semibold">Add an admin</h3>
        <div className="relative">
          <label htmlFor="team-user" className="block text-sm font-medium mb-1">Discord name or user ID</label>
          {picked ? (
            <div className="flex items-center justify-between rounded border border-primary bg-bg-elevated px-3 py-2 text-sm">
              <span>{picked.display_name} <span className="text-text-muted text-xs">({picked.user_id})</span></span>
              <button type="button" className="text-text-muted hover:text-text" onClick={() => setPicked(null)} aria-label="Clear">
                ✕
              </button>
            </div>
          ) : (
            <input
              id="team-user"
              className={`${inputCls} w-full`}
              placeholder="Start typing a name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
            />
          )}
          {results.length > 0 && !picked && (
            <ul className="absolute z-10 mt-1 w-full bg-bg-elevated border border-border rounded shadow-harsh max-h-56 overflow-y-auto">
              {results.map((u) => (
                <li key={u.user_id}>
                  <button
                    type="button"
                    className="w-full text-left px-3 py-2 text-sm hover:bg-secondary/10"
                    onClick={() => { setPicked(u); setResults([]) }}
                  >
                    {u.display_name} <span className="text-text-muted text-xs">({u.user_id})</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <label htmlFor="team-role" className="block text-sm font-medium mb-1">Role</label>
          <select id="team-role" className={`${inputCls} w-full`} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="manager">{ROLE_LABELS.manager}</option>
            <option value="fulfillment">{ROLE_LABELS.fulfillment}</option>
          </select>
        </div>
        <p className="text-xs text-text-muted">
          They&apos;ll see Store Admin in their menu after signing in with Discord, limited to {storefront.name}.
        </p>
        {error && <p className="text-accent-red text-sm">{error}</p>}
        <button
          type="button"
          onClick={add}
          disabled={!target || busy}
          className="w-full bg-primary hover:bg-primary-dark text-white font-medium px-4 py-2 rounded transition-colors disabled:opacity-50"
        >
          Add to {storefront.name}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- Storefronts

function StorefrontEditor({ storefront, onSaved }) {
  const [form, setForm] = useState({
    name: storefront.name || '',
    description: storefront.description || '',
    contact_email: storefront.contact_email || '',
    shipping: storefront.shipping_cents == null ? '' : (storefront.shipping_cents / 100).toFixed(2),
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const save = async (extra = {}) => {
    setBusy(true)
    setError(null)
    try {
      const { shipping, ...fields } = form
      if (!storefront.uses_summit_stripe) {
        fields.shipping_cents = shipping === '' ? null : Math.round(parseFloat(shipping) * 100)
      }
      await adminUpdateStorefront(storefront.id, { ...fields, ...extra })
      onSaved()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="px-4 py-4 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{storefront.name}</span>
        <span className="text-xs text-text-muted font-mono">/store?storefront={storefront.slug}</span>
        <span className={`text-xs ${storefront.is_active ? 'text-accent-green' : 'text-text-muted'}`}>
          {storefront.is_active ? 'Live' : 'Hidden'}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <input className={inputCls} aria-label={`${storefront.name} name`} value={form.name} onChange={set('name')} />
        <input className={inputCls} aria-label={`${storefront.name} contact email`} placeholder="Contact email for buyers" value={form.contact_email} onChange={set('contact_email')} />
        <textarea className={`${inputCls} sm:col-span-2`} aria-label={`${storefront.name} description`} placeholder="Short description shown under the tab" rows={2} value={form.description} onChange={set('description')} />
        {!storefront.uses_summit_stripe && (
          <label className="text-sm text-text-muted flex items-center gap-2">
            Flat shipping $
            <input
              className={`${inputCls} w-24`}
              aria-label={`${storefront.name} shipping`}
              type="number" min="0" step="0.01"
              placeholder="Default"
              value={form.shipping}
              onChange={set('shipping')}
            />
          </label>
        )}
      </div>
      <p className="text-xs text-text-muted">
        {storefront.uses_summit_stripe
          ? "Payments go to Summit's Stripe account."
          : storefront.accepts_payments
            ? `Payments go to its own Stripe account (${storefront.stripe_account_id}).`
            : storefront.stripe_account_id
              ? 'Stripe setup started but not finished. Not taking orders yet.'
              : 'No Stripe account connected. Not taking orders yet.'}
      </p>
      {error && <p className="text-accent-red text-sm">{error}</p>}
      <div className="flex gap-4 text-sm">
        <button type="button" disabled={busy} onClick={() => save()} className="text-primary hover:underline disabled:opacity-50">
          Save
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => save({ is_active: !storefront.is_active })}
          className="text-primary hover:underline disabled:opacity-50"
        >
          {storefront.is_active ? 'Hide storefront' : 'Show storefront'}
        </button>
        {storefront.stripe_account_id && (
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              if (!window.confirm(`Disconnect ${storefront.name}'s Stripe account? It will stop taking orders.`)) return
              setBusy(true)
              try {
                await adminDisconnectStripe(storefront.id)
                onSaved()
              } catch (e) {
                setError(e.message)
              } finally {
                setBusy(false)
              }
            }}
            className="text-accent-red hover:underline disabled:opacity-50"
          >
            Disconnect Stripe
          </button>
        )}
      </div>
    </li>
  )
}

function ApplicationRow({ app, onDone }) {
  const [slug, setSlug] = useState(
    app.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const act = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onDone()
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <li className="px-4 py-4 space-y-2 text-sm">
      <div className="flex flex-wrap justify-between gap-2">
        <span className="font-semibold text-base">{app.name}</span>
        <span className="text-text-muted">from {app.username} · {new Date(app.created_at).toLocaleDateString()}</span>
      </div>
      <p className="text-text-muted whitespace-pre-line">{app.description}</p>
      <p><span className="text-text-muted">Shipping:</span> {app.shipping}</p>
      <p>
        <span className="text-text-muted">Team:</span> {app.username} (manager)
        {(app.team || []).map((m) => (
          <span key={m.user_id}>, {m.username} ({m.role === 'manager' ? 'manager' : 'shipper'})</span>
        ))}
      </p>
      <p>
        <span className="text-text-muted">Contact:</span> {app.contact_email}
        {app.website && <> · <a href={app.website} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{app.website}</a></>}
      </p>
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <label className="text-text-muted" htmlFor={`slug-${app.id}`}>Web address</label>
        <input id={`slug-${app.id}`} className={`${inputCls} w-48 py-1`} value={slug} onChange={(e) => setSlug(e.target.value)} />
        <button
          type="button"
          disabled={busy}
          onClick={() => act(() => adminApproveStorefrontApplication(app.id, slug))}
          className="bg-accent-green text-white font-medium px-3 py-1.5 rounded disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => act(() => adminDeclineStorefrontApplication(app.id))}
          className="text-accent-red hover:underline disabled:opacity-50"
        >
          Decline
        </button>
      </div>
      {error && <p className="text-accent-red">{error}</p>}
    </li>
  )
}

function StorefrontsPanel({ storefronts, onChanged }) {
  const [apps, setApps] = useState([])
  const [newName, setNewName] = useState('')
  const [error, setError] = useState(null)

  const loadApps = useCallback(() => {
    adminGetStorefrontApplications('pending')
      .then((d) => setApps(d.applications || []))
      .catch((e) => setError(e.message))
  }, [])
  useEffect(loadApps, [loadApps])

  const create = async () => {
    setError(null)
    try {
      await adminCreateStorefront({ name: newName.trim() })
      setNewName('')
      onChanged()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="space-y-8">
      <section>
        <h2 className="font-semibold text-lg mb-3">Applications</h2>
        {apps.length === 0 ? (
          <p className="text-sm text-text-muted">No applications waiting.</p>
        ) : (
          <ul className="bg-bg-surface border border-border rounded-lg divide-y divide-border">
            {apps.map((a) => (
              <ApplicationRow key={a.id} app={a} onDone={() => { loadApps(); onChanged() }} />
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="font-semibold text-lg mb-3">Storefronts</h2>
        <ul className="bg-bg-surface border border-border rounded-lg divide-y divide-border mb-4">
          {storefronts.map((sf) => (
            <StorefrontEditor key={`${sf.id}-${sf.updated_at}`} storefront={sf} onSaved={onChanged} />
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <input
            className={`${inputCls} flex-1 min-w-48`}
            placeholder="New storefront name"
            aria-label="New storefront name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button
            type="button"
            onClick={create}
            disabled={!newName.trim()}
            className="bg-primary hover:bg-primary-dark text-white font-medium px-4 py-2 rounded transition-colors disabled:opacity-50"
          >
            New storefront
          </button>
        </div>
        {error && <p className="text-accent-red text-sm mt-2">{error}</p>}
      </section>
    </div>
  )
}

// ---------------------------------------------------------------- Payments

function PaymentsCard({ storefront, canConnect, checkStripe, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Back from Stripe's onboarding pages: ask Stripe whether it's done
  useEffect(() => {
    if (!checkStripe || !storefront.stripe_account_id) return
    adminGetStorefrontPayments(storefront.id, true)
      .then((d) => { if (d.accepts_payments !== storefront.accepts_payments) onChanged() })
      .catch((e) => setError(e.message))
  }, [checkStripe, storefront.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (storefront.accepts_payments) {
    return (
      <p className="text-xs text-text-muted mb-2">
        {storefront.name} takes payments on its own Stripe account.
      </p>
    )
  }

  const connect = async () => {
    setBusy(true)
    setError(null)
    try {
      const { url } = await adminStartStripeOnboarding(storefront.id)
      window.location.assign(url)
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  const recheck = async () => {
    setBusy(true)
    setError(null)
    try {
      const d = await adminGetStorefrontPayments(storefront.id, true)
      if (d.accepts_payments) onChanged()
      else setError('Stripe says setup still isn\'t finished.')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const started = Boolean(storefront.stripe_account_id)
  return (
    <div className="bg-secondary/10 border border-secondary/30 rounded-lg px-4 py-3 my-3 text-sm">
      <p className="mb-2">
        {started
          ? `${storefront.name}'s Stripe setup isn't finished, so it can't take orders yet.`
          : `${storefront.name} can't take orders until it connects its own Stripe account. Payments go straight to that account.`}
      </p>
      {canConnect ? (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={connect}
            disabled={busy}
            className="bg-primary hover:bg-primary-dark text-white font-medium px-4 py-2 rounded transition-colors disabled:opacity-50"
          >
            {started ? 'Finish Stripe setup' : 'Connect Stripe'}
          </button>
          {started && (
            <button type="button" onClick={recheck} disabled={busy} className="text-primary hover:underline disabled:opacity-50">
              Check again
            </button>
          )}
        </div>
      ) : (
        <p className="text-text-muted">A manager of {storefront.name} can connect it.</p>
      )}
      {error && <p className="text-accent-red mt-2">{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------- Page

export default function StoreAdmin() {
  usePageTitle('Store Admin')
  const [me, setMe] = useState(null)
  const [error, setError] = useState(null)
  const [params] = useSearchParams()
  // ?storefront=<id> opens one storefront (Stripe onboarding returns here)
  const [storefrontId, setStorefrontId] = useState(
    params.get('storefront') ? Number(params.get('storefront')) : undefined,
  ) // null = all
  const backFromStripe = params.get('stripe') === 'return'
  const [tab, setTab] = useState('orders')

  const loadMe = useCallback(() => {
    adminGetMe()
      .then((d) => {
        setMe(d)
        setStorefrontId((current) => {
          if (current !== undefined) return current
          // With a single storefront there's nothing to switch between
          return d.storefronts.length === 1 ? d.storefronts[0].id : null
        })
      })
      .catch((e) => setError(e.message))
  }, [])
  useEffect(loadMe, [loadMe])

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!me) return <Spinner className="py-20" />

  const full = me.is_full_admin
  const storefronts = me.storefronts || []
  const selected = storefronts.find((sf) => sf.id === storefrontId) || null
  const canEditProducts = full || (selected
    ? selected.role === 'manager'
    : storefronts.some((sf) => sf.role === 'manager'))
  const productStorefronts = full ? storefronts : storefronts.filter((sf) => sf.role === 'manager')

  const tabs = [
    { key: 'orders', label: 'Order queue' },
    canEditProducts && { key: 'products', label: 'Products' },
    full && { key: 'team', label: 'Admins' },
    full && { key: 'storefronts', label: 'Storefronts' },
  ].filter(Boolean)
  const current = tabs.some((t) => t.key === tab) ? tab : 'orders'
  const pills = storefronts.length > 1
    ? [{ id: null, name: 'All storefronts' }, ...storefronts]
    : storefronts

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-display text-secondary">Store Admin</h1>
        {full && (
          <a
            href="/api/store/admin/backup"
            className="text-sm text-primary hover:underline"
            download
          >
            Download backup
          </a>
        )}
      </div>

      {current !== 'storefronts' && (
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <span className="text-sm text-text-muted mr-1">Managing</span>
          {pills.map((sf) => (
            <button
              key={sf.id ?? 'all'}
              type="button"
              aria-pressed={storefrontId === sf.id}
              onClick={() => setStorefrontId(sf.id)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                storefrontId === sf.id
                  ? 'bg-brand-blue border-brand-blue-light text-white'
                  : 'border-border text-text-muted hover:text-text'
              }`}
            >
              {sf.name}
            </button>
          ))}
        </div>
      )}
      {selected && !selected.uses_summit_stripe && current !== 'storefronts' && (
        <PaymentsCard
          key={selected.id}
          storefront={selected}
          canConnect={full || selected.role === 'manager'}
          checkStripe={backFromStripe}
          onChanged={loadMe}
        />
      )}
      {!full && (
        <p className="text-xs text-text-muted mb-2">
          You can manage {storefronts.map((sf) => sf.name).join(', ')} only.
        </p>
      )}

      <div className="flex gap-2 border-b border-border mb-6 mt-4">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              current === t.key
                ? 'border-secondary text-secondary'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {current === 'orders' && (
        <OrdersPanel key={storefrontId ?? 'all'} storefrontId={storefrontId} showStorefront={storefrontId == null} />
      )}
      {current === 'products' && (
        <ProductsPanel key={storefrontId ?? 'all'} storefrontId={storefrontId} storefronts={productStorefronts} />
      )}
      {current === 'team' && (
        selected
          ? <TeamPanel key={selected.id} storefront={selected} />
          : <p className="text-sm text-text-muted">Pick a storefront above to see and change its admins.</p>
      )}
      {current === 'storefronts' && <StorefrontsPanel storefronts={storefronts} onChanged={loadMe} />}
    </div>
  )
}
