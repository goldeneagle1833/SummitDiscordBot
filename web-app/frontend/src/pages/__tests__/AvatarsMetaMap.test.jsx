import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { screen, renderWithRouter, waitFor } from '@/test/test-utils'
import Avatars from '../Avatars'
import { getAvatars, getAvatarFilters } from '@/api/cards'

vi.mock('@/api/cards', () => ({
  getAvatars: vi.fn(),
  getAvatarImageFiles: vi.fn(() => Promise.resolve([])),
  getAvatarFilters: vi.fn(),
  getPlayDrawStats: vi.fn(() => Promise.resolve(null)),
  getSeasonStats: vi.fn(() => Promise.resolve([])),
}))
vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('@/api/admin', () => ({ getAvatarImageSettings: vi.fn(() => Promise.resolve({})) }))
vi.mock('@/api/client', () => ({ get: vi.fn(() => Promise.resolve(null)) }))
vi.mock('@/components/ui/DataReleaseNote', () => ({ default: () => null }))

const row = (name, total, wins) => ({ name, total, wins, losses: total - wins, win_rate: Math.round((wins / total) * 1000) / 10, avatar_score: 50 })
const ALL = [row('Sparkmage', 300, 170), row('Witch', 200, 90)]
const SEASON_8 = [row('Pathfinder', 120, 70), row('Seer', 80, 35)]

describe('Avatars page meta map', () => {
  beforeEach(() => {
    sessionStorage.clear()
    getAvatarFilters.mockResolvedValue({ events: [{ event_id: 8, event_name: 'Season 8', is_active: false }], sources: [] })
    getAvatars.mockImplementation((params) => Promise.resolve(params?.event === '8' ? SEASON_8 : ALL))
  })

  const dotNames = () => [...document.querySelectorAll('section[aria-labelledby="avatar-meta-map"] circle title')].map((t) => t.textContent.split(':')[0])

  it('redraws for the chosen event', async () => {
    renderWithRouter(<Avatars />)
    await waitFor(() => expect(dotNames()).toEqual(expect.arrayContaining(['Sparkmage', 'Witch'])))
    await screen.findByRole('option', { name: 'Season 8' })
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: '8' } })
    await waitFor(() => expect(dotNames()).toEqual(expect.arrayContaining(['Pathfinder', 'Seer'])))
    expect(dotNames()).not.toContain('Sparkmage')
  })

  it('collapses and remembers it for the session', async () => {
    const { unmount } = renderWithRouter(<Avatars />)
    const toggle = await screen.findByRole('button', { name: /Avatar Meta Map/ })
    await waitFor(() => expect(dotNames().length).toBe(2))
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(dotNames()).toEqual([])
    expect(sessionStorage.getItem('avatars.metaMapOpen')).toBe('0')
    unmount()
    renderWithRouter(<Avatars />)
    const again = await screen.findByRole('button', { name: /Avatar Meta Map/ })
    expect(again).toHaveAttribute('aria-expanded', 'false')
  })
})
