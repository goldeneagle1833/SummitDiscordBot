import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('@/api/client', () => ({ get: vi.fn(() => Promise.resolve({})) }))
vi.mock('@/api/store', () => ({ getProducts: vi.fn(), getStorefronts: vi.fn() }))

import { getProducts, getStorefronts } from '@/api/store'
import { StoreCard } from '../Home'

describe('StoreCard', () => {
  beforeEach(() => {
    getProducts.mockReset()
    getStorefronts.mockReset()
    getStorefronts.mockResolvedValue({
      storefronts: [
        { id: 1, slug: 'summit', name: 'Summit Store' },
        { id: 2, slug: 'explorer-series', name: 'Explorer Series' },
      ],
    })
    getProducts.mockResolvedValue({
      products: [
        { id: 1, storefront_id: 1, images: ['/static/store/a.jpg'] },
        { id: 2, storefront_id: 1, images: [], image_url: '/static/store/b.jpg' },
        { id: 3, storefront_id: 1, images: [] },
        { id: 4, storefront_id: 2, images: ['/static/store/explorer.jpg'] },
      ],
    })
  })

  it('stays "coming soon" with no photo before launch', () => {
    renderWithRouter(<StoreCard live={false} />)
    expect(screen.getByText('Coming soon')).toBeInTheDocument()
    expect(getProducts).not.toHaveBeenCalled()
    expect(screen.queryByTestId('store-card-bg')).not.toBeInTheDocument()
  })

  it('uses a photo from one of the listings once live', async () => {
    renderWithRouter(<StoreCard live />)
    const img = await screen.findByTestId('store-card-bg')
    expect(['/static/store/a.jpg', '/static/store/b.jpg']).toContain(img.getAttribute('src'))
    expect(screen.getByRole('link', { name: 'Shop Summit Store' })).toHaveAttribute('href', '/store')
  })

  it('never uses a photo from another storefront', async () => {
    getProducts.mockResolvedValue({
      products: [{ id: 4, storefront_id: 2, images: ['/static/store/explorer.jpg'] }],
    })
    renderWithRouter(<StoreCard live />)
    await screen.findByRole('link', { name: 'Shop Summit Store' })
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByTestId('store-card-bg')).not.toBeInTheDocument()
  })
})
