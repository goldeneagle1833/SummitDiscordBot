import { get, post } from './client'

// Buyer
export const getProducts = () => get('/api/store/products')
export const getCheckoutPrefill = () => get('/api/store/checkout/prefill')
export const createCheckout = (payload) => post('/api/store/checkout', payload)
export const getMyOrders = () => get('/api/store/orders/mine')

// Store admin
export const adminGetProducts = () => get('/api/store/admin/products')
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
export const adminGetOrders = (status) =>
  get(`/api/store/admin/orders${status ? `?status=${status}` : ''}`)
export const adminGetOrder = (id) => get(`/api/store/admin/orders/${id}`)
export const adminShipOrder = (id, tracking_number, tracking_carrier) =>
  post(`/api/store/admin/orders/${id}/ship`, { tracking_number, tracking_carrier })
export const adminSetOrderStatus = (id, status) =>
  post(`/api/store/admin/orders/${id}/status`, { status })

export const formatMoney = (cents, currency = 'USD') =>
  currency === 'USD'
    ? `$${(cents / 100).toFixed(2)}`
    : `${(cents / 100).toFixed(2)} ${currency}`
