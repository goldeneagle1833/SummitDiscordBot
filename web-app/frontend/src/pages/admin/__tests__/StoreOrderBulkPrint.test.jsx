import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { Routes, Route } from 'react-router-dom'
import { screen, renderWithRouter, waitFor } from '@/test/test-utils'

vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, adminGetOrder: vi.fn() }
})

import { adminGetOrder } from '@/api/store'
import StoreOrderBulkPrint, { packagesFor } from '../StoreOrderBulkPrint'

const base = {
  username: 'buyer', status: 'paid', currency: 'USD', subtotal_cents: 599, shipping_cents: 199,
  tax_cents: 0, total_cents: 798, ship_line1: '1 Main St', ship_city: 'Columbus', ship_state: 'OH',
  ship_postal: '43004', ship_country: 'US', created_at: '2026-11-10T12:00:00+00:00',
  items: [{ id: 1, product_name: 'Island Leviathan Pack', unit_price_cents: 599, quantity: 1 }],
}
const ORDERS = {
  1: { ...base, id: 1, order_number: 'SUM-1', ship_name: 'Ann One' },
  2: { ...base, id: 2, order_number: 'SUM-2', ship_name: 'Bob Two', ship_group: 'g1', items: [{ id: 2, product_name: 'Full Playset', unit_price_cents: 1499, quantity: 1 }] },
  3: { ...base, id: 3, order_number: 'SUM-3', ship_name: 'Cat Three' },
  4: { ...base, id: 4, order_number: 'SUM-4', ship_name: 'Bob Two', ship_group: 'g1' },
}

function renderBulk(route) {
  return renderWithRouter(
    <Routes>
      <Route path="/admin/store/orders/print" element={<StoreOrderBulkPrint />} />
    </Routes>,
    { route },
  )
}

describe('packagesFor', () => {
  it('keeps paired orders together and keeps list order', () => {
    const pk = packagesFor([ORDERS[1], ORDERS[2], ORDERS[3], ORDERS[4]])
    expect(pk.map((p) => p.map((o) => o.id))).toEqual([[1], [2, 4], [3]])
  })
})

describe('StoreOrderBulkPrint', () => {
  let printSpy
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    adminGetOrder.mockReset()
    adminGetOrder.mockImplementation((id) => (ORDERS[id] ? Promise.resolve({ order: ORDERS[id] }) : Promise.reject(new Error('Not found'))))
    printSpy = vi.fn()
    window.print = printSpy
  })
  afterEach(() => { vi.useRealTimers() })

  it('renders one slip per package, pairs on one slip', async () => {
    renderBulk('/admin/store/orders/print?ids=1,2,3,4')
    await screen.findByText(/3 packing slips, one per page/)
    expect(adminGetOrder).toHaveBeenCalledTimes(4)
    expect(document.querySelectorAll('.slip')).toHaveLength(3)
    expect(screen.getAllByText('Order Numbers: SUM-2, SUM-4').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Order Number: SUM-1').length).toBeGreaterThan(0)
    expect(printSpy).not.toHaveBeenCalled()
  })

  it('auto-prints once loaded and notes orders that failed', async () => {
    renderBulk('/admin/store/orders/print?print=1&ids=1,99')
    await screen.findByText(/1 order couldn't load/)
    vi.advanceTimersByTime(400)
    await waitFor(() => expect(printSpy).toHaveBeenCalledTimes(1))
  })

  it('says so when nothing was picked', () => {
    renderBulk('/admin/store/orders/print?ids=')
    expect(screen.getByText('No orders picked to print.')).toBeInTheDocument()
  })
})
