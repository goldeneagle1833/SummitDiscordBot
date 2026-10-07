import { get, post, patch, del } from './client'

// Buyer
export const getProducts = () => get('/api/store/products')
export const getStorefronts = () => get('/api/store/storefronts')
export const applyForStorefront = (data) => post('/api/store/storefront-applications', data)
export const getMyStorefrontApplications = () => get('/api/store/storefront-applications/mine')
export const getCheckoutPrefill = () => get('/api/store/checkout/prefill')
export const createCheckout = (payload) => post('/api/store/checkout', payload)
export const getMyOrders = () => get('/api/store/orders/mine')
export const cancelMyOrder = (orderNumber) =>
  post(`/api/store/orders/${encodeURIComponent(orderNumber)}/cancel`)

// Web notifications
export const getWebNotifications = () => get('/api/store/notifications')
export const dismissNotification = (id) => post(`/api/store/notifications/${id}/dismiss`)

// Admin: view a user's orders
export const adminGetUserOrders = (userId) => get(`/api/store/orders/user/${userId}`)

// Store admin
export const adminGetMe = () => get('/api/store/admin/me')
export const adminGetProducts = (storefrontId) =>
  get(`/api/store/admin/products${storefrontId ? `?storefront_id=${storefrontId}` : ''}`)
export const adminCreateProduct = (data) => post('/api/store/admin/products', data)
export const adminUpdateProduct = (id, data) =>
  fetch(`/api/store/admin/products/${id}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(async (res) => {
    if (!res.ok) {
      const d = await res.json().catch(() => ({}))
      throw new Error(d.error || res.statusText)
    }
    return res.json()
  })
export const adminDeactivateProduct = (id) =>
  post(`/api/store/admin/products/${id}/deactivate`)
// Uploads one or more image files; resolves to { url, urls } in upload order.
export const adminUploadProductImages = (files) => {
  const fd = new FormData()
  for (const file of files) fd.append('image', file)
  return fetch('/api/store/admin/products/upload-image', {
    method: 'POST',
    body: fd,
    credentials: 'include',
  }).then(async (res) => {
    const d = await res.json().catch(() => ({}))
    if (!res.ok || !d.success) throw new Error(d.error || res.statusText)
    return d
  })
}
export const adminGetOrders = (filters = {}) => {
  const params = new URLSearchParams()
  if (filters.storefront_id) params.set('storefront_id', filters.storefront_id)
  if (filters.status) params.set('status', filters.status)
  if (filters.product_id) params.set('product_id', filters.product_id)
  if (filters.search) params.set('search', filters.search)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  const qs = params.toString()
  return get(`/api/store/admin/orders${qs ? `?${qs}` : ''}`)
}
export const adminGetOrder = (id) => get(`/api/store/admin/orders/${id}`)
export const adminShipOrder = (id, tracking_number, tracking_carrier) =>
  post(`/api/store/admin/orders/${id}/ship`, { tracking_number, tracking_carrier })
export const adminSetOrderStatus = (id, status) =>
  post(`/api/store/admin/orders/${id}/status`, { status })

// Storefronts, their admins, and applications (full store admins)
export const adminCreateStorefront = (data) => post('/api/store/admin/storefronts', data)
export const adminUpdateStorefront = (id, data) => patch(`/api/store/admin/storefronts/${id}`, data)
export const adminGetStorefrontAdmins = (id) => get(`/api/store/admin/storefronts/${id}/admins`)
export const adminAddStorefrontAdmin = (id, data) =>
  post(`/api/store/admin/storefronts/${id}/admins`, data)
export const adminRemoveStorefrontAdmin = (id, userId) =>
  del(`/api/store/admin/storefronts/${id}/admins/${encodeURIComponent(userId)}`)
export const adminSearchUsers = (q) => get(`/api/store/admin/user-search?q=${encodeURIComponent(q)}`)
// Each storefront's own Stripe account
export const adminGetStorefrontPayments = (id, refresh = false) =>
  get(`/api/store/admin/storefronts/${id}/stripe${refresh ? '?refresh=1' : ''}`)
export const adminStartStripeOnboarding = (id) =>
  post(`/api/store/admin/storefronts/${id}/stripe/onboard`)
export const adminDisconnectStripe = (id) => del(`/api/store/admin/storefronts/${id}/stripe`)

export const adminGetStorefrontApplications = (status) =>
  get(`/api/store/admin/storefront-applications${status ? `?status=${status}` : ''}`)
export const adminApproveStorefrontApplication = (id, slug) =>
  post(`/api/store/admin/storefront-applications/${id}/approve`, slug ? { slug } : {})
export const adminDeclineStorefrontApplication = (id) =>
  post(`/api/store/admin/storefront-applications/${id}/decline`)

export const formatMoney = (cents, currency = 'USD') =>
  currency === 'USD'
    ? `$${(cents / 100).toFixed(2)}`
    : `${(cents / 100).toFixed(2)} ${currency}`
