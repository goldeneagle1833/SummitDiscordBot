import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'

const post = vi.fn(() => Promise.resolve({ success: true }))

vi.mock('@/api/client', () => ({
  post: (...a) => post(...a),
  del: vi.fn(),
  get: vi.fn((url) => {
    if (url === '/api/analytics/banners/active') {
      return Promise.resolve({ success: true, banners: [{ id: 5, title: 'Gift Guide', link: 'https://youtu.be/x', color: 'purple', badge_text: 'COMMUNITY' }] })
    }
    if (url === '/api/analytics/promo-layout') {
      return Promise.resolve({
        success: true,
        layout: { order: ['staff-pick', 'promo-5'], hidden: ['spotlight'] },
        banners: [
          { id: 5, title: 'Gift Guide', link: 'https://youtu.be/x', color: 'purple', badge_text: 'COMMUNITY', active: true, created_by: 'content-bot', expires_at: '2999-01-01 00:00:00', images: [] },
          { id: 6, title: 'Old sale', link: '/store', color: 'blue', badge_text: 'NEW', active: false, created_by: 'AdminUser', expires_at: '2999-01-01 00:00:00', images: [] },
        ],
      })
    }
    if (url === '/api/deck-rec/staff-pick') {
      return Promise.resolve({ success: true, staff_pick: { deck_name: 'Burn', avatar_name: 'Sparkmage', deck_id: 3 } })
    }
    if (url === '/api/analytics/banners') return Promise.resolve({ success: true, banners: [] })
    return Promise.resolve({})
  }),
}))
vi.mock('@/api/articles', () => ({
  listArticles: () => Promise.resolve({ articles: [] }), articleImage: () => null, articlePath: () => '/a',
}))

import HomePromos from '../HomePromos'

const rowTitles = () => Array.from(document.querySelectorAll('[data-slot]')).map(li => li.dataset.slot)

describe('HomePromos admin', () => {
  beforeEach(() => post.mockClear())

  it('lists every slot in the saved order with on/off state', async () => {
    renderWithRouter(<HomePromos />)
    await waitFor(() => expect(screen.getByText('Gift Guide')).toBeTruthy())
    const rows = rowTitles()
    expect(rows.indexOf('promo-5')).toBe(rows.indexOf('staff-pick') + 1)
    expect(rowTitles()).toContain('promo-6')
    expect(screen.getByText('Burn')).toBeTruthy()
    expect(screen.getByRole('switch', { name: /Daily spotlight/ }).getAttribute('aria-checked')).toBe('false')
    expect(screen.getByRole('switch', { name: /Old sale/ }).getAttribute('aria-checked')).toBe('false')
    // Staff pick and the shared video are the two slides showing
    expect(screen.getByText(/showing on the home page now/).textContent).toContain('2')
  })

  it('saves a move and a switch flip', async () => {
    renderWithRouter(<HomePromos />)
    await waitFor(() => expect(screen.getByText('Gift Guide')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Move Gift Guide up' }))
    await waitFor(() => expect(post).toHaveBeenCalled())
    let [, body] = post.mock.calls.at(-1)
    expect(body.order.indexOf('staff-pick')).toBe(body.order.indexOf('promo-5') + 1)
    expect(body.off).toEqual(expect.arrayContaining(['spotlight', 'promo-6']))

    fireEvent.click(screen.getByRole('switch', { name: /Turn off Gift Guide/ }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    ;[, body] = post.mock.calls.at(-1)
    expect(body.off).toContain('promo-5')
  })
})
