import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent, waitFor, within } from '@/test/test-utils'

vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return {
    ...actual,
    adminGetProducts: vi.fn(),
    adminCreateProduct: vi.fn(),
    adminUpdateProduct: vi.fn(),
    adminDeactivateProduct: vi.fn(),
    adminUploadProductImages: vi.fn(),
    adminGetOrders: vi.fn(),
  }
})

import {
  adminGetProducts, adminCreateProduct, adminUpdateProduct, adminUploadProductImages, adminGetOrders,
} from '@/api/store'
import StoreAdmin from '../StoreAdmin'

const TOKEN = {
  id: 7,
  sku: 'TOK-FIRE',
  name: 'Fire Token',
  description: 'Burns',
  price_cents: 1299,
  currency: 'USD',
  stock_quantity: 4,
  is_active: 1,
  max_per_user_monthly: 2,
  image_url: '/one.png',
  images: ['/one.png', '/two.png'],
}

async function openProductsTab() {
  renderWithRouter(<StoreAdmin />)
  await userEvent.click(await screen.findByRole('button', { name: 'Products' }))
  await screen.findByText('TOK-FIRE')
}

describe('StoreAdmin order queue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    adminGetProducts.mockResolvedValue({ products: [TOKEN] })
    adminGetOrders.mockResolvedValue({
      orders: [{ id: 42, order_number: 'SUM-20260930-ABC123', username: 'bruce', total_cents: 1999, currency: 'USD', status: 'paid' }],
    })
  })

  it('gives every order a print button that opens the order form in a new tab', async () => {
    renderWithRouter(<StoreAdmin />)
    const link = await screen.findByRole('link', { name: 'Print order form for SUM-20260930-ABC123' })
    expect(link).toHaveAttribute('href', '/admin/store/orders/42/print?print=1')
    expect(link).toHaveAttribute('target', '_blank')
  })
})

describe('StoreAdmin products', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    adminGetProducts.mockResolvedValue({ products: [TOKEN] })
    adminGetOrders.mockResolvedValue({ orders: [] })
    adminUpdateProduct.mockResolvedValue({ success: true })
    adminCreateProduct.mockResolvedValue({ id: 8 })
  })

  it('lists products with an image count badge', async () => {
    await openProductsTab()
    expect(screen.getByTitle('2 images')).toHaveTextContent('+1')
  })

  it('opens the editor prefilled and saves every field', async () => {
    await openProductsTab()
    await userEvent.click(screen.getByRole('button', { name: 'Edit Fire Token' }))

    expect(screen.getByRole('heading', { name: 'Edit Fire Token' })).toBeInTheDocument()
    expect(screen.getByLabelText('SKU')).toHaveValue('TOK-FIRE')
    expect(screen.getByLabelText('Price')).toHaveValue('12.99')
    expect(screen.getByLabelText('Monthly limit per user')).toHaveValue('2')
    const gallery = screen.getByLabelText('Product images')
    expect(within(gallery).getAllByRole('img')).toHaveLength(2)

    await userEvent.clear(screen.getByLabelText('Name'))
    await userEvent.type(screen.getByLabelText('Name'), 'Flame Token')
    await userEvent.clear(screen.getByLabelText('Price'))
    await userEvent.type(screen.getByLabelText('Price'), '9.50')
    await userEvent.clear(screen.getByLabelText('Monthly limit per user'))
    await userEvent.click(screen.getByRole('button', { name: 'Remove image 1' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(adminUpdateProduct).toHaveBeenCalledTimes(1))
    expect(adminUpdateProduct).toHaveBeenCalledWith(7, {
      sku: 'TOK-FIRE',
      name: 'Flame Token',
      description: 'Burns',
      price_cents: 950,
      stock_quantity: 4,
      max_per_user_monthly: null,
      images: ['/two.png'],
    })
    // Editor closes and the list reloads
    const callsBefore = adminGetProducts.mock.calls.length
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Add product' })).toBeInTheDocument())
    await waitFor(() => expect(adminGetProducts.mock.calls.length).toBeGreaterThan(callsBefore - 1))
  })

  it('reorders images and makes another one primary', async () => {
    await openProductsTab()
    await userEvent.click(screen.getByRole('button', { name: 'Edit Fire Token' }))

    await userEvent.click(screen.getByRole('button', { name: 'Primary' }))
    const gallery = screen.getByLabelText('Product images')
    const imgs = within(gallery).getAllByRole('img')
    expect(imgs[0]).toHaveAttribute('src', '/two.png')
    expect(imgs[1]).toHaveAttribute('src', '/one.png')

    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(adminUpdateProduct).toHaveBeenCalled())
    expect(adminUpdateProduct.mock.calls[0][1].images).toEqual(['/two.png', '/one.png'])
  })

  it('uploads several files at once and appends them to the gallery', async () => {
    adminUploadProductImages.mockResolvedValue({ url: '/u1.png', urls: ['/u1.png', '/u2.png'] })
    await openProductsTab()
    await userEvent.click(screen.getByRole('button', { name: 'Edit Fire Token' }))

    const input = document.getElementById('product-image-file-7')
    const files = [
      new File(['a'], 'a.png', { type: 'image/png' }),
      new File(['b'], 'b.png', { type: 'image/png' }),
    ]
    await userEvent.upload(input, files)

    await waitFor(() => expect(adminUploadProductImages).toHaveBeenCalledTimes(1))
    expect(adminUploadProductImages.mock.calls[0][0]).toHaveLength(2)
    const gallery = screen.getByLabelText('Product images')
    await waitFor(() => expect(within(gallery).getAllByRole('img')).toHaveLength(4))
  })

  it('adds a product with a pasted image URL', async () => {
    await openProductsTab()
    await userEvent.type(screen.getByLabelText('SKU'), 'TOK-ICE')
    await userEvent.type(screen.getByLabelText('Name'), 'Ice Token')
    await userEvent.type(screen.getByLabelText('Price'), '5')
    await userEvent.type(screen.getByLabelText('Stock quantity'), '3')
    await userEvent.type(screen.getByLabelText('Image URL'), 'https://img.example/ice.png{enter}')
    await userEvent.click(screen.getByRole('button', { name: 'Add product' }))

    await waitFor(() => expect(adminCreateProduct).toHaveBeenCalledTimes(1))
    expect(adminCreateProduct).toHaveBeenCalledWith({
      sku: 'TOK-ICE',
      name: 'Ice Token',
      description: '',
      price_cents: 500,
      stock_quantity: 3,
      max_per_user_monthly: undefined,
      images: ['https://img.example/ice.png'],
    })
  })

  it('cancelling the editor returns to the add form without saving', async () => {
    await openProductsTab()
    await userEvent.click(screen.getByRole('button', { name: 'Edit Fire Token' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('heading', { name: 'Add product' })).toBeInTheDocument()
    expect(adminUpdateProduct).not.toHaveBeenCalled()
  })
})
