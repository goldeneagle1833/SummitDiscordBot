import { describe, it, expect, vi } from 'vitest'

vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('@/api/client', () => ({ get: vi.fn(() => Promise.resolve({})), post: vi.fn(), del: vi.fn(), ApiError: Error }))

import { articleSlide } from '../Home'

describe('articleSlide', () => {
  it('is nothing without a new article', () => {
    expect(articleSlide(null)).toBeNull()
  })

  it('links to the article and uses an outside page image', () => {
    const slide = articleSlide({
      id: 7, slug: 'the-pv-rule', title: 'The PV Rule', summary: 'Why it matters.',
      author_name: 'grish', external_site: 'Eternal Durdles', external_image: 'https://eternaldurdles.com/i.png',
    })
    expect(slide).toMatchObject({
      badge: 'NEW ARTICLE', title: 'The PV Rule', subtitle: 'Why it matters.',
      extra: 'By grish on Eternal Durdles', link: '/articles/7-the-pv-rule',
      thumbnail: 'https://eternaldurdles.com/i.png', cta: 'Read article',
    })
  })
})
