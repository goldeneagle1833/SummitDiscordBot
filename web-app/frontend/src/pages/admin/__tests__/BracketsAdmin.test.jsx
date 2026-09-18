import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import BracketsAdmin from '../BracketsAdmin'
import {
  adminListBrackets,
  adminGetBracket,
  adminGetSeedPool,
  adminSyncTickets,
  adminCreateBracket,
  adminSetEntrants,
  adminShuffleSeeds,
  adminMoveEntrant,
  adminPublishBracket,
  adminPreviewBracket,
} from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  adminListBrackets: vi.fn(),
  adminGetBracket: vi.fn(),
  adminGetSeedPool: vi.fn(),
  adminSyncTickets: vi.fn(),
  adminCreateBracket: vi.fn(),
  adminSetEntrants: vi.fn(),
  adminShuffleSeeds: vi.fn(),
  adminMoveEntrant: vi.fn(),
  adminPublishBracket: vi.fn(),
  adminPreviewBracket: vi.fn(),
  adminUnpublishBracket: vi.fn(),
  adminDeleteBracket: vi.fn(),
}))

vi.mock('@/api/admin', () => ({ searchUsers: vi.fn() }))

const DRAFT = {
  slug: 'season-7',
  name: 'Season 7 Postseason',
  status: 'draft',
  entrant_count: 3,
  champion: null,
}

describe('BracketsAdmin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    adminListBrackets.mockResolvedValue({ brackets: [DRAFT] })
    adminGetBracket.mockResolvedValue({
      bracket: DRAFT,
      entrants: [
        { seed: 1, display_name: 'One', user_id: 'u1', elo: 1900, is_ticket_holder: 1 },
        { seed: 2, display_name: 'Two', user_id: 'u2', elo: 1800, is_ticket_holder: 1 },
        { seed: 3, display_name: 'Three', user_id: 'u3', elo: 1700, is_ticket_holder: 0 },
      ],
      rounds: [],
    })
    adminGetSeedPool.mockResolvedValue({
      players: [{ user_id: 'u1', display_name: 'One' }],
      event: { event_name: 'Season 7' },
      ticket_filter_applied: true,
      ticket_roster_size: 24,
      ticket_sync_configured: true,
    })
    adminShuffleSeeds.mockResolvedValue({ entrant_count: 3 })
    adminMoveEntrant.mockResolvedValue({ entrant_count: 3 })
    adminSetEntrants.mockResolvedValue({ entrant_count: 2 })
    adminPublishBracket.mockResolvedValue({ entrant_count: 3, byes: 1 })
    adminPreviewBracket.mockResolvedValue({
      bracket_size: 4,
      byes: 1,
      entrants: [],
      rounds: [
        {
          round: 1,
          title: 'Semifinals',
          matches: [
            {
              match_no: 2,
              round_title: 'Semifinals',
              state: 'pending',
              playable: true,
              p1_seed: 2,
              p1_name: 'Two',
              p2_seed: 3,
              p2_name: 'Three',
              p1_from_bye: false,
              p2_from_bye: false,
            },
          ],
        },
        {
          round: 2,
          title: 'Finals',
          matches: [
            {
              match_no: 3,
              round_title: 'Finals',
              state: 'pending',
              playable: false,
              p1_seed: 1,
              p1_name: 'One',
              p2_seed: null,
              p2_name: null,
              p1_from_bye: true,
              p2_from_bye: false,
            },
          ],
        },
      ],
    })
  })

  it('creates a draft with a chosen starting count', async () => {
    adminCreateBracket.mockResolvedValue({
      slug: 'new-cup',
      entrant_count: 24,
      requested_size: 24,
      short_by: 0,
    })
    renderWithRouter(<BracketsAdmin />)

    await userEvent.type(screen.getByLabelText('Name'), 'New Cup')
    const size = screen.getByLabelText(/Starting players/i)
    await userEvent.clear(size)
    await userEvent.type(size, '24')
    await userEvent.click(screen.getByRole('button', { name: /create draft/i }))

    await waitFor(() =>
      expect(adminCreateBracket).toHaveBeenCalledWith({
        name: 'New Cup',
        size: 24,
        source: 'ticket_holders',
      }),
    )
    expect(await screen.findByText(/Created with 24 seeded players/)).toBeInTheDocument()
  })

  it('says how short the pool was', async () => {
    adminCreateBracket.mockResolvedValue({
      slug: 'new-cup',
      entrant_count: 9,
      requested_size: 16,
      short_by: 7,
    })
    renderWithRouter(<BracketsAdmin />)

    await userEvent.type(screen.getByLabelText('Name'), 'Small Cup')
    await userEvent.click(screen.getByRole('button', { name: /create draft/i }))

    expect(await screen.findByText(/7 short of 16/)).toBeInTheDocument()
  })

  it('shows that the ticket-holder filter is in effect', async () => {
    renderWithRouter(<BracketsAdmin />)
    expect(await screen.findByText(/Filtered to 24 ticket holders/)).toBeInTheDocument()
  })

  it('warns and offers a sync when no ticket roster exists', async () => {
    adminGetSeedPool.mockResolvedValue({
      players: [],
      event: null,
      ticket_filter_applied: false,
      ticket_roster_size: 0,
      ticket_sync_configured: true,
    })
    adminSyncTickets.mockResolvedValue({ count: 24 })
    renderWithRouter(<BracketsAdmin />)

    expect(await screen.findByText(/No ticket-holder roster synced/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /sync from discord/i }))
    expect(await screen.findByText(/Synced 24 ticket holders/)).toBeInTheDocument()
  })

  it('reports a failed ticket sync', async () => {
    adminGetSeedPool.mockResolvedValue({
      players: [],
      event: null,
      ticket_filter_applied: false,
      ticket_roster_size: 0,
    })
    adminSyncTickets.mockRejectedValue(new Error('No Discord bot token configured'))
    renderWithRouter(<BracketsAdmin />)

    await userEvent.click(await screen.findByRole('button', { name: /sync from discord/i }))
    expect(await screen.findByText(/No Discord bot token configured/)).toBeInTheDocument()
  })

  it('lists drafts as not yet visible to players', async () => {
    renderWithRouter(<BracketsAdmin />)
    expect(await screen.findByText(/Draft — not visible to players/)).toBeInTheDocument()
  })

  it('edits seeds: move, shuffle and remove', async () => {
    renderWithRouter(<BracketsAdmin />)
    await userEvent.click(await screen.findByRole('button', { name: /edit seeds/i }))

    expect(await screen.findByText('Seeding (3)')).toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('Move Three up'))
    expect(adminMoveEntrant).toHaveBeenCalledWith('season-7', 3, 2)

    await userEvent.click(screen.getByRole('button', { name: 'Shuffle' }))
    expect(adminShuffleSeeds).toHaveBeenCalledWith('season-7')

    await userEvent.click(screen.getByLabelText('Remove Two'))
    expect(adminSetEntrants).toHaveBeenCalledWith(
      'season-7',
      expect.arrayContaining([expect.objectContaining({ display_name: 'One' })]),
    )
    expect(adminSetEntrants.mock.calls[0][1]).toHaveLength(2)
  })

  it('previews the bracket the current seeding would produce', async () => {
    renderWithRouter(<BracketsAdmin />)
    await userEvent.click(await screen.findByRole('button', { name: /edit seeds/i }))

    expect(await screen.findByText('Preview')).toBeInTheDocument()
    expect(
      screen.getByText(/3 players in a 4-slot bracket/),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/top seed gets a first-round bye and starts in round 2/),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Semifinals' })).toBeInTheDocument()
    // The bye player is shown in round two, tagged, with no first-round card.
    expect(screen.getByText('bye')).toBeInTheDocument()
  })

  it('reorders by dragging a name onto a seed', async () => {
    renderWithRouter(<BracketsAdmin />)
    await userEvent.click(await screen.findByRole('button', { name: /edit seeds/i }))

    const rows = await screen.findAllByRole('listitem')
    const store = {}
    const dataTransfer = {
      setData: (_, value) => {
        store.value = value
      },
      getData: () => store.value,
      effectAllowed: '',
    }

    fireEvent.dragStart(rows[2], { dataTransfer })
    fireEvent.dragOver(rows[0], { dataTransfer })
    fireEvent.drop(rows[0], { dataTransfer })

    await waitFor(() => expect(adminMoveEntrant).toHaveBeenCalledWith('season-7', 3, 1))
  })

  it('swaps two players dropped on each other in the preview', async () => {
    renderWithRouter(<BracketsAdmin />)
    await userEvent.click(await screen.findByRole('button', { name: /edit seeds/i }))
    const previewPanel = (await screen.findByText('Preview')).closest('div')

    const store = {}
    const dataTransfer = {
      setData: (_, value) => {
        store.value = value
      },
      getData: () => store.value,
    }

    // Names appear in both the seed list and the preview; drag the preview ones.
    fireEvent.dragStart(within(previewPanel).getByText('Two'), { dataTransfer })
    fireEvent.drop(within(previewPanel).getByText('Three'), { dataTransfer })

    await waitFor(() => expect(adminSetEntrants).toHaveBeenCalled())
    const sent = adminSetEntrants.mock.calls[0][1]
    // Seeds 2 and 3 traded places; seed 1 stayed put.
    expect(sent.map((e) => e.display_name)).toEqual(['One', 'Three', 'Two'])
  })

  it('cannot move the top seed any higher', async () => {
    renderWithRouter(<BracketsAdmin />)
    await userEvent.click(await screen.findByRole('button', { name: /edit seeds/i }))
    expect(await screen.findByLabelText('Move One up')).toBeDisabled()
    expect(screen.getByLabelText('Move Three down')).toBeDisabled()
  })

  it('publishes a draft', async () => {
    renderWithRouter(<BracketsAdmin />)
    await userEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    await waitFor(() => expect(adminPublishBracket).toHaveBeenCalledWith('season-7'))
  })

  it('shows a publish failure', async () => {
    adminPublishBracket.mockRejectedValue(new Error('A bracket needs at least 2 entrants'))
    renderWithRouter(<BracketsAdmin />)
    await userEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    expect(await screen.findByText(/at least 2 entrants/)).toBeInTheDocument()
  })

  it('offers view and unpublish once published', async () => {
    adminListBrackets.mockResolvedValue({
      brackets: [{ ...DRAFT, status: 'published' }],
    })
    renderWithRouter(<BracketsAdmin />)

    expect(await screen.findByText('View')).toHaveAttribute('href', '/brackets/season-7')
    expect(screen.getByRole('button', { name: 'Unpublish' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit seeds/i })).not.toBeInTheDocument()
  })
})
