import { describe, it, expect, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import * as api from '@/api/paperFinishes'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import PaperBadges from '../PaperBadges'

const row = (over) => ({
  folder: 'f', event: 'Event', event_date_display: '2026', place: 1, label: 'Winner', avatar: 'Druid',
  deck_id: 'd', names: ['Someone'], name_source: 'deck owner', posted_by: 'Someone', status: 'auto',
  name_key: 'someone', player: { user_id: '1', name: 'Someone' }, candidates: [], earns_badge: true,
  ...over,
})

vi.mock('@/api/players', () => ({
  searchPlayers: vi.fn(() => Promise.resolve({ players: [{ user_id: '9', display_name: 'Geoffrey' }] })),
}))

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
    manual: [
      { manual_id: 7, folder: 'manual-7', manual: true, event: 'Store Champs', event_date: '2026-10-04', event_date_display: 'Oct 4, 2026', place: 2, label: 'Finalist', avatar: '', player: { user_id: '2', name: 'Avaloneer' }, set_by: 'Bruce' },
    ],
    badge_only: [
      { event_id: 'cmt1', folder: 'sorcery-cmt1', name: 'Columbus Store Champs', event_url: 'https://sorcerytcg.com/events/cmt1', event_date: '2026-10-25', event_date_display: 'Oct 25, 2026', top_cut: 4, players: 12, top_cut_names: ['Avaloneer', 'Kevin F', 'Ptg', 'Sam'] },
    ],
  })),
  addManualPaperResult: vi.fn(() => Promise.resolve({ success: true })),
  updateManualPaperResult: vi.fn(() => Promise.resolve({ success: true })),
  deleteManualPaperResult: vi.fn(() => Promise.resolve({ success: true })),
  linkPaperName: vi.fn(), rejectPaperName: vi.fn(), unlinkPaperName: vi.fn(),
  assignPaperResult: vi.fn(), clearPaperResult: vi.fn(), setPaperEventBadges: vi.fn(),
  getPaperFinishes: vi.fn(),
  importBadgeOnlyEvent: vi.fn(() => Promise.resolve({ success: true, name: 'Dayton Locals', players: 9, top_cut: 8, updated: false })),
  updateBadgeOnlyEvent: vi.fn(() => Promise.resolve({ success: true })),
  deleteBadgeOnlyEvent: vi.fn(() => Promise.resolve({ success: true })),
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

describe('PaperBadges manual results', () => {
  it('adds a result for a chosen player, Winner by default', async () => {
    renderWithRouter(<PaperBadges />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add a result by hand' }))
    expect(screen.getByText('Store Champs')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add result' }))
    expect(screen.getByText('Pick a player first.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Choose player' }))
    fireEvent.change(screen.getByPlaceholderText('Search Summit players...'), { target: { value: 'geo' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Geoffrey' }, { timeout: 2000 }))
    fireEvent.change(screen.getByPlaceholderText('e.g. Store Championship'), { target: { value: 'Card Shop Open' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add result' }))
    await waitFor(() => expect(api.addManualPaperResult).toHaveBeenCalledWith({
      user_id: '9', event: 'Card Shop Open', event_date: null, place: 1, avatar: null,
    }))
  })

  it('edits and removes a hand-added result', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithRouter(<PaperBadges />)
    fireEvent.click(await screen.findByRole('tab', { name: /Added by hand/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByDisplayValue('Store Champs')).toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('Finalist'), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(api.updateManualPaperResult).toHaveBeenCalledWith(7, {
      user_id: '2', event: 'Store Champs', event_date: '2026-10-04', place: 4, avatar: null,
    }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(api.deleteManualPaperResult).toHaveBeenCalledWith(7))
  })

  it('adds, edits and removes an event with no deck lists', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithRouter(<PaperBadges />)
    fireEvent.click(await screen.findByRole('tab', { name: /No deck lists/ }))
    const link = screen.getByRole('link', { name: 'Columbus Store Champs' })
    expect(link).toHaveAttribute('href', 'https://sorcerytcg.com/events/cmt1')
    expect(screen.getByText(/12 players · Top 4 get badges/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add event' }))
    expect(await screen.findByText(/Paste a sorcerytcg.com event link/)).toBeInTheDocument()
    expect(api.importBadgeOnlyEvent).not.toHaveBeenCalled()

    fireEvent.change(screen.getByPlaceholderText('https://sorcerytcg.com/events/...'), { target: { value: 'https://sorcerytcg.com/events/cmt2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add event' }))
    await waitFor(() => expect(api.importBadgeOnlyEvent).toHaveBeenCalledWith({ event_url: 'https://sorcerytcg.com/events/cmt2', name: undefined, top_cut: 'auto' }))
    expect(await screen.findByText(/Added Dayton Locals: 9 players, top 8 get badges/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByDisplayValue('Columbus Store Champs'), { target: { value: 'Columbus Champs' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.updateBadgeOnlyEvent).toHaveBeenCalledWith('cmt1', { name: 'Columbus Champs', event_date: '2026-10-25', top_cut: 4 }))

    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(api.deleteBadgeOnlyEvent).toHaveBeenCalledWith('cmt1'))
  })
})
