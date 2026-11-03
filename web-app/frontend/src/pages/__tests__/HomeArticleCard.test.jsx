import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'

vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('@/api/client', () => ({ get: vi.fn(() => Promise.resolve({})), post: vi.fn(), del: vi.fn(), ApiError: Error }))

import { NewArticleCard } from '../Home'

const base = {
  id: 7, slug: 'frog-tempo', title: 'Frog Tempo Primer', category: 'Deck Guide',
  author_name: 'Kate', external_url: null, external_site: null, external_image: null,
}

describe('NewArticleCard', () => {
  it('links to the article and shows the author', () => {
    renderWithRouter(<NewArticleCard article={base} />)
    expect(screen.getByText('New article')).toBeInTheDocument()
    expect(screen.getByText('Player Article · Kate')).toBeInTheDocument()
    const links = screen.getAllByRole('link')
    expect(links.every((a) => a.getAttribute('href') === '/articles/7-frog-tempo')).toBe(true)
  })

  it('uses the linked page image and site for outside articles', () => {
    renderWithRouter(<NewArticleCard article={{
      ...base, external_url: 'https://eternaldurdles.com/x', external_site: 'Eternal Durdles',
      external_image: 'https://eternaldurdles.com/i.png',
    }} />)
    expect(screen.getByText('Player Article · Kate · Eternal Durdles')).toBeInTheDocument()
    expect(document.querySelector('img').getAttribute('src')).toBe('https://eternaldurdles.com/i.png')
  })
})
