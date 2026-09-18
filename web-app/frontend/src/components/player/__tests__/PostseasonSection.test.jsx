import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import PostseasonSection from '../PostseasonSection'
import { getPlayerPostseason } from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  getPlayerPostseason: vi.fn(),
  getBracketMarks: vi.fn(),
}))

const ENTRIES = [
  {
    slug: 'gothic-6',
    name: 'Gothic Season 6 Postseason',
    status: 'complete',
    entrants: 24,
    seed: 4,
    placement: 1,
    label: 'Champion',
    wins: 4,
    losses: 0,
    played_at: '2026-09-18T13:40:30',
  },
  {
    slug: 'gothic-5',
    name: 'Gothic Season 5 Postseason',
    status: 'complete',
    entrants: 16,
    seed: 9,
    placement: 5,
    label: 'Top 8',
    wins: 1,
    losses: 1,
    played_at: '2026-06-02T10:00:00',
  },
]

describe('PostseasonSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPlayerPostseason.mockResolvedValue({ brackets: ENTRIES })
  })

  it('lists each bracket with the finish', async () => {
    renderWithRouter(<PostseasonSection playerId="u1" />)
    expect(await screen.findByText('Postseason')).toBeInTheDocument()
    expect(screen.getByText('Champion')).toBeInTheDocument()
    expect(screen.getByText('Top 8')).toBeInTheDocument()
  })

  it('shows the seed, field size and record', async () => {
    renderWithRouter(<PostseasonSection playerId="u1" />)
    expect(await screen.findByText(/seed 4 of 24 · 4-0/)).toBeInTheDocument()
    expect(screen.getByText(/seed 9 of 16 · 1-1/)).toBeInTheDocument()
  })

  it('marks a win with a yurt', async () => {
    const { container } = renderWithRouter(<PostseasonSection playerId="u1" />)
    await screen.findByText('Champion')
    // One yurt for the bracket they won, none for the top 8.
    expect(container.querySelectorAll('img')).toHaveLength(1)
  })

  it('links each bracket', async () => {
    renderWithRouter(<PostseasonSection playerId="u1" />)
    expect(await screen.findByText('Gothic Season 6 Postseason')).toHaveAttribute(
      'href',
      '/brackets/gothic-6',
    )
  })

  it('stays hidden for a player who has never been in one', async () => {
    getPlayerPostseason.mockResolvedValue({ brackets: [] })
    const { container } = renderWithRouter(<PostseasonSection playerId="u1" />)
    await waitFor(() => expect(getPlayerPostseason).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('stays hidden when the lookup fails', async () => {
    getPlayerPostseason.mockRejectedValue(new Error('nope'))
    const { container } = renderWithRouter(<PostseasonSection playerId="u1" />)
    await waitFor(() => expect(getPlayerPostseason).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
