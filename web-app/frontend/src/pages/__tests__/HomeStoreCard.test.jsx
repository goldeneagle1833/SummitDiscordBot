import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('@/api/client', () => ({ get: vi.fn(() => Promise.resolve({})) }))
vi.mock('@/api/store', () => ({ getProducts: vi.fn() }))

import { getProducts } from '@/api/store'
import { StoreCard } from '../Home'

describe('StoreCard', () => {
  beforeEach(() => {
    getProducts.mockReset()
    getProducts.mockResolvedValue({
      products: [
        { id: 1, images: ['/static/store/a.jpg'] },
        { id: 2, images: [], image_url: '/static/store/b.jpg' },
        { id: 3, images: [] },
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
})
