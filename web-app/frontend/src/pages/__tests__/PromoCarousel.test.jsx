import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'

vi.mock('@/api/client', () => ({
  get: vi.fn((url) => {
    if (url === '/api/analytics/banners/active') {
      return Promise.resolve({
        success: true,
        banners: [
          { id: 1, title: 'First Slide', subtitle: '', link: '/first', color: 'blue', badge_text: 'NEWS' },
          { id: 2, title: 'Second Slide', subtitle: '', link: '/second', color: 'blue', badge_text: 'NEWS' },
        ],
      })
    }
    return Promise.resolve({})
  }),
}))

import { PromoCarousel } from '../Home'

const slideLink = (title) => screen.getByText(title).closest('a')
const isShown = (title) => slideLink(title).style.opacity === '1'

function swipe(el, fromX, toX, { y = 100, dy = 0 } = {}) {
  fireEvent.touchStart(el, { touches: [{ clientX: fromX, clientY: y }] })
  fireEvent.touchMove(el, { touches: [{ clientX: (fromX + toX) / 2, clientY: y + dy / 2 }] })
  fireEvent.touchMove(el, { touches: [{ clientX: toX, clientY: y + dy }] })
  fireEvent.touchEnd(el, { changedTouches: [{ clientX: toX, clientY: y + dy }] })
}

describe('PromoCarousel swipe', () => {
  beforeEach(() => {
    navigator.sendBeacon = vi.fn()
  })

  it('advances on a left swipe and swallows the trailing click', async () => {
    renderWithRouter(<PromoCarousel />)
    await waitFor(() => expect(isShown('First Slide')).toBe(true))

    const first = slideLink('First Slide')
    swipe(first, 300, 150)
    fireEvent.click(first)

    expect(isShown('Second Slide')).toBe(true)
    expect(navigator.sendBeacon).not.toHaveBeenCalled()
  })

  it('goes back on a right swipe', async () => {
    renderWithRouter(<PromoCarousel />)
    await waitFor(() => expect(isShown('First Slide')).toBe(true))

    swipe(slideLink('First Slide'), 100, 250)
    expect(isShown('Second Slide')).toBe(true) // wraps around
  })

  it('ignores vertical scrolls and still lets taps through', async () => {
    renderWithRouter(<PromoCarousel />)
    await waitFor(() => expect(isShown('First Slide')).toBe(true))

    const first = slideLink('First Slide')
    swipe(first, 200, 210, { dy: 120 })
    expect(isShown('First Slide')).toBe(true)

    fireEvent.click(first)
    expect(navigator.sendBeacon).toHaveBeenCalledTimes(1)
  })
})
