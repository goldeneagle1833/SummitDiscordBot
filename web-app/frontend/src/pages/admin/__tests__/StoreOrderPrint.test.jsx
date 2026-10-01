import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { Routes, Route } from 'react-router-dom'
import { screen, renderWithRouter, waitFor, within } from '@/test/test-utils'

vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, adminGetOrder: vi.fn() }
})

import { adminGetOrder } from '@/api/store'
import StoreOrderPrint from '../StoreOrderPrint'

const ORDER = {
  id: 42,
  order_number: 'SUM-20260930-ABC123',
  username: 'bruce',
  email: 'bruce@example.com',
  auth_provider: 'discord',
  status: 'paid',
  currency: 'USD',
  subtotal_cents: 1500,
  shipping_cents: 599,
  tax_cents: 0,
  total_cents: 2099,
  ship_name: 'Bruce Wayne',
  ship_line1: '1007 Mountain Dr',
  ship_line2: '',
  ship_city: 'Gotham',
  ship_state: 'NJ',
  ship_postal: '07001',
  ship_country: 'US',
  created_at: '2026-09-30T22:53:40+00:00',
  paid_at: '2026-09-30T22:55:22+00:00',
  items: [
    { id: 1, sku: 'TOK-FIRE', product_name: 'Fire Token', unit_price_cents: 500, quantity: 2 },
    { id: 2, sku: 'TOK-ICE', product_name: 'Ice Token', unit_price_cents: 500, quantity: 1 },
  ],
}

function renderPrint(route) {
  return renderWithRouter(
    <Routes>
      <Route path="/admin/store/orders/:id/print" element={<StoreOrderPrint />} />
    </Routes>,
    { route },
  )
}

describe('StoreOrderPrint', () => {
  let printSpy

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    adminGetOrder.mockReset()
    printSpy = vi.fn()
    window.print = printSpy
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the order as a packing slip', async () => {
    adminGetOrder.mockResolvedValue({ order: ORDER })
    renderPrint('/admin/store/orders/42/print')

    await screen.findAllByText('Order Number: SUM-20260930-ABC123')
    expect(adminGetOrder).toHaveBeenCalledWith('42')

    // Address appears twice: the bold ship-to block and the shipping address column
    expect(screen.getAllByText('Bruce Wayne')).toHaveLength(2)
    expect(screen.getAllByText('1007 Mountain Dr')).toHaveLength(2)
    expect(screen.getAllByText('Gotham, NJ 07001')).toHaveLength(2)

    // Order details
    expect(screen.getByText('Sep 30, 2026')).toBeInTheDocument()
    expect(screen.getByText('Standard')).toBeInTheDocument()
    expect(screen.getByText('bruce')).toBeInTheDocument()
    expect(screen.getByText('bruce@example.com')).toBeInTheDocument()

    // Line items with quantity, price and line total, then the total row
    expect(screen.getByText('Fire Token')).toBeInTheDocument()
    expect(screen.getByText('(TOK-FIRE)')).toBeInTheDocument()
    expect(screen.getByText('$10.00')).toBeInTheDocument()
    const totalRow = screen.getByText('Total').closest('tr')
    expect(within(totalRow).getByText('3')).toBeInTheDocument()
    expect(within(totalRow).getByText('$15.00')).toBeInTheDocument()

    // Shipping and order total
    expect(screen.getByText('$5.99')).toBeInTheDocument()
    expect(screen.getByText('$20.99')).toBeInTheDocument()

    // Footer repeats the order number with the page count
    expect(screen.getAllByText('Order Number: SUM-20260930-ABC123')).toHaveLength(2)
    expect(screen.getByText('1 of 1')).toBeInTheDocument()
  })

  it('labels free shipping and shows tracking when shipped', async () => {
    adminGetOrder.mockResolvedValue({
      order: { ...ORDER, shipping_cents: 0, tracking_number: '9400111899', tracking_carrier: 'USPS' },
    })
    renderPrint('/admin/store/orders/42/print')
    await screen.findAllByText('Order Number: SUM-20260930-ABC123')
    expect(screen.getByText(/Free shipping/)).toBeInTheDocument()
    expect(screen.getByText(/USPS 9400111899/)).toBeInTheDocument()
  })

  it('does not print on its own without ?print=1', async () => {
    adminGetOrder.mockResolvedValue({ order: ORDER })
    renderPrint('/admin/store/orders/42/print')
    await screen.findAllByText('Order Number: SUM-20260930-ABC123')
    await vi.advanceTimersByTimeAsync(500)
    expect(printSpy).not.toHaveBeenCalled()
  })

  it('opens the print dialog once the order has loaded when ?print=1', async () => {
    adminGetOrder.mockResolvedValue({ order: ORDER })
    renderPrint('/admin/store/orders/42/print?print=1')
    await screen.findAllByText('Order Number: SUM-20260930-ABC123')
    await vi.advanceTimersByTimeAsync(500)
    await waitFor(() => expect(printSpy).toHaveBeenCalledTimes(1))
  })

  it('says so when the order has no shipping address', async () => {
    adminGetOrder.mockResolvedValue({
      order: { ...ORDER, ship_name: '', ship_line1: '', ship_city: '', ship_state: '', ship_postal: '', ship_country: '' },
    })
    renderPrint('/admin/store/orders/42/print')
    expect((await screen.findAllByText('No shipping address on file')).length).toBeGreaterThan(0)
  })

  it('shows the API error instead of a blank page', async () => {
    adminGetOrder.mockRejectedValue(new Error('Order not found'))
    renderPrint('/admin/store/orders/999/print')
    expect(await screen.findByText('Order not found')).toBeInTheDocument()
  })
})
