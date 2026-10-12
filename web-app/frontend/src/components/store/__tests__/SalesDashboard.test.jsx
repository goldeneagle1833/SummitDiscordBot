import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent } from '@/test/test-utils'

vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, adminGetDashboard: vi.fn(), adminGetOrderMap: vi.fn() }
})

import { adminGetDashboard, adminGetOrderMap } from '@/api/store'
import SalesDashboard from '../SalesDashboard'

const DATA = {
  days: 30,
  totals: { sales_cents: 490000, orders: 40, units: 90, average_cents: 12250 },
  previous: { sales_cents: 400000, orders: 40, units: 100, average_cents: 10000 },
  daily: [{ date: '2026-10-11', sales_cents: 1000, unfinished_cents: 500 }, { date: '2026-10-12', sales_cents: 2000, unfinished_cents: 0 }],
  attention: { to_ship: 3, oldest_to_ship_at: null, awaiting_payment: 1, unfinished_week: 2, unfinished_week_cents: 1600, low_stock: [{ id: 1, name: 'Playmat', stock: 0 }], flagged: 0 },
  top_products: [{ product_id: 1, name: 'Fire token set', units: 12, sales_cents: 6000 }],
  money: { products_cents: 400000, shipping_cents: 90000, tax_cents: 0, refunded_cents: 2800, refunded_orders: 1 },
  repeat_buyers: { buyers: 30, repeat: 6, best: [{ user_id: '1', username: 'beadylittleeyes', orders: 3, spent_cents: 4500 }] },
  ship_time: { shipped: 4, average_hours: 30, median_hours: 20, within_2_days: 3 },
  limit_hits: [{ product_id: 1, name: 'Fire token set', cap: 2, buyers: 9, hits: 4 }],
  states: [{ state: 'OH', orders: 20, sales_cents: 250000 }, { state: 'TX', orders: 5, sales_cents: 60000 }, { state: '?', orders: 1, sales_cents: 500 }],
}

describe('SalesDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    try { localStorage.clear() } catch { /* ignore */ }
    adminGetDashboard.mockResolvedValue(DATA)
  })

  it('shows the totals and the extra cards', async () => {
    renderWithRouter(<SalesDashboard storefrontId={1} title="Summit Store" />)
    expect(await screen.findByText('$4,900')).toBeInTheDocument()
    expect(screen.getAllByText('▲ 23% vs the 30 days before')).toHaveLength(2)
    expect(screen.getByText('▼ 10% vs the 30 days before')).toBeInTheDocument()
    expect(screen.getByText('Playmat (sold out)')).toBeInTheDocument()
    expect(screen.getByText('beadylittleeyes')).toBeInTheDocument()
    expect(screen.getByText('30 hours')).toBeInTheDocument()
    expect(screen.getByText('4 hits')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Monthly sales CSV' })).toHaveAttribute('href', '/api/store/admin/sales-summary.csv?storefront_id=1')
    expect(adminGetDashboard).toHaveBeenCalledWith(1, 30)
  })

  it('changes range and can be hidden', async () => {
    renderWithRouter(<SalesDashboard storefrontId={null} title="All storefronts" />)
    await screen.findByText('$4,900')
    await userEvent.click(screen.getByRole('button', { name: '90 days' }))
    expect(adminGetDashboard).toHaveBeenLastCalledWith(null, 90)
    await userEvent.click(screen.getByRole('button', { name: 'Hide' }))
    expect(screen.getByRole('button', { name: 'Show sales' })).toBeInTheDocument()
  })

  it('lists states and opens the order map', async () => {
    vi.mock('@/components/explorer/SeriesMap', () => ({
      default: ({ points }) => <div data-testid="map">{points.map((p) => p.title).join(' | ')}</div>,
    }))
    adminGetOrderMap.mockResolvedValue({
      places: [{ city: 'Columbus', state: 'OH', orders: 3, sales_cents: 4900, latitude: 40, longitude: -83 }],
      locating: 2, not_found: 0,
    })
    renderWithRouter(<SalesDashboard storefrontId={2} title="Explorer Series Store" />)
    expect(await screen.findByText('Ohio')).toBeInTheDocument()
    expect(screen.getByText('Texas')).toBeInTheDocument()
    expect(screen.getByText('No state given')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Open the order map/ }))
    expect(await screen.findByTestId('map')).toHaveTextContent('Columbus, Ohio')
    expect(screen.getByText(/2 cities are still being placed/)).toBeInTheDocument()
    expect(adminGetOrderMap).toHaveBeenCalledWith(2, 30)
  })
})
