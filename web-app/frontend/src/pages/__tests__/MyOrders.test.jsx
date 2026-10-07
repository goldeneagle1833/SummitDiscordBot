import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent } from '@/test/test-utils'

vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, getMyOrders: vi.fn() }
})

import { getMyOrders } from '@/api/store'
import MyOrders from '../MyOrders'

const order = (num, slug, name, extra = {}) => ({
  order_number: num, storefront_slug: slug, storefront_name: name, status: 'paid',
  total_cents: 500, currency: 'USD', created_at: '2026-10-01T00:00:00Z', items: [], ...extra,
})

describe('MyOrders page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows a tab per storefront and filters orders by it', async () => {
    getMyOrders.mockResolvedValue({ orders: [
      order('SUM-1', 'summit', 'Summit Store'),
      order('EXP-1', 'explorer', 'Explorer Store'),
      order('SUM-2', 'summit', 'Summit Store'),
    ] })
    renderWithRouter(<MyOrders />)
    expect(await screen.findByRole('tab', { name: /All orders 3/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /Summit Store 2/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: /Explorer Store 1/ }))
    expect(screen.getByText('EXP-1')).toBeInTheDocument()
    expect(screen.queryByText('SUM-1')).not.toBeInTheDocument()
  })

  it('links buyers to the storefront contact email', async () => {
    getMyOrders.mockResolvedValue({ orders: [
      order('EXP-1', 'explorer', 'Explorer Store', { storefront_contact_email: 'shop@explorer.test' }),
    ] })
    renderWithRouter(<MyOrders />)
    await userEvent.click(await screen.findByText('EXP-1'))
    expect(screen.getByRole('link', { name: 'Contact Explorer Store' })).toHaveAttribute('href', 'mailto:shop@explorer.test')
  })

  it('shows an empty state with no orders', async () => {
    getMyOrders.mockResolvedValue({ orders: [] })
    renderWithRouter(<MyOrders />)
    expect(await screen.findByText('No orders yet.')).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })
})
