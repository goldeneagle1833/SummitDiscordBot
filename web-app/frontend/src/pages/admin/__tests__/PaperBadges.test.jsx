import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import PaperBadges from '../PaperBadges'

const row = (over) => ({
  folder: 'f', event: 'Event', event_date_display: '2026', place: 1, label: 'Winner', avatar: 'Druid',
  deck_id: 'd', names: ['Someone'], name_source: 'deck owner', posted_by: 'Someone', status: 'auto',
  name_key: 'someone', player: { user_id: '1', name: 'Someone' }, candidates: [], earns_badge: true,
  ...over,
})

vi.mock('@/api/paperFinishes', () => ({
  getPaperFinishesReview: vi.fn(() => Promise.resolve({
    events: [
      { folder: 'a', name: 'SCG Con Atlanta', awards_badges: true, default_on: true },
      { folder: 'b', name: 'LinCon', awards_badges: true, default_on: true },
    ],
    results: [
      row({ folder: 'a', event: 'SCG Con Atlanta', names: ['PeterTheGreat'], player: { user_id: '1', name: 'PeterTheGreat' } }),
      row({ folder: 'b', event: 'LinCon', place: 2, names: ['Avaloneer'], player: { user_id: '2', name: 'Avaloneer' } }),
      row({ folder: 'a', event: 'SCG Con Atlanta', place: 3, names: ['Paladin'], player: { user_id: '3', name: 'paladin_of_io' } }),
    ],
    links: [],
  })),
  linkPaperName: vi.fn(), rejectPaperName: vi.fn(), unlinkPaperName: vi.fn(),
  assignPaperResult: vi.fn(), clearPaperResult: vi.fn(), setPaperEventBadges: vi.fn(),
  getPaperFinishes: vi.fn(),
}))

describe('PaperBadges search', () => {
  it('filters results by player name and by event name', async () => {
    renderWithRouter(<PaperBadges />)
    fireEvent.click(await screen.findByRole('tab', { name: /Badges given/ }))
    expect(screen.getAllByText('SCG Con Atlanta')).toHaveLength(2)

    fireEvent.change(screen.getByLabelText('Search player name'), { target: { value: 'paladin' } })
    expect(screen.getByText('paladin_of_io')).toBeInTheDocument()
    expect(screen.queryByText('PeterTheGreat')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search player name'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Search event name'), { target: { value: 'lincon' } })
    expect(screen.getByRole('link', { name: 'Avaloneer' })).toBeInTheDocument()
    expect(screen.queryByText('SCG Con Atlanta')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /Events/ }))
    expect(screen.getByText('LinCon')).toBeInTheDocument()
    expect(screen.queryByText('SCG Con Atlanta')).not.toBeInTheDocument()
  })
})
