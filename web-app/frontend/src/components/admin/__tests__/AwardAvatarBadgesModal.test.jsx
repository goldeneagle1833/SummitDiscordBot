import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const preview = {
  folder: 'Houston',
  event: 'Houston',
  source: 'top_cut',
  field_size: 8,
  awarded: [],
  avatars: [
    { avatar: 'Druid', place: 1, finish: 'Winner', avatar_players: 4, status: 'linked', player: { user_id: '1', name: 'Duo' } },
    { avatar: 'Avatar of Air', place: 2, finish: 'Finalist', avatar_players: 1, status: 'unmatched', paper_name: 'Informant118', player: null },
    { avatar: 'Deathspeaker', place: 5, finish: 'Top 8', avatar_players: 1, status: 'linked', player: { user_id: '2', name: 'FRANEKSTEIN' } },
  ],
}

const award = vi.fn()
vi.mock('@/api/paperFinishes', () => ({
  previewEventAvatarBadges: vi.fn(() => Promise.resolve(preview)),
  awardEventAvatarBadges: (...args) => award(...args),
  undoEventAvatarBadges: vi.fn(),
}))
vi.mock('@/api/cards', () => ({ getAvatarImageFiles: vi.fn(() => Promise.resolve([])) }))

import AwardAvatarBadgesModal from '../AwardAvatarBadgesModal'

describe('AwardAvatarBadgesModal', () => {
  beforeEach(() => award.mockReset())

  it('awards only the ticked avatars', async () => {
    award.mockResolvedValue({ ...preview, awarded: [{ avatar: 'Deathspeaker', user_id: '2' }] })
    render(<MemoryRouter><AwardAvatarBadgesModal folder="Houston" onClose={() => {}} /></MemoryRouter>)

    const druid = await screen.findByLabelText('Give the Druid badge')
    expect(druid).toBeChecked()
    expect(screen.getByLabelText('Give the Avatar of Air badge')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Award 2 badges' })).toBeEnabled()

    fireEvent.click(druid)
    fireEvent.click(screen.getByRole('button', { name: 'Award 1 badge' }))
    await waitFor(() => expect(award).toHaveBeenCalledWith('Houston', ['Deathspeaker']))
    expect(await screen.findByText('1 badge awarded.')).toBeInTheDocument()
    expect(screen.getByLabelText('Give the Druid badge')).not.toBeChecked()
  })

  it('cannot award with nothing ticked', async () => {
    render(<MemoryRouter><AwardAvatarBadgesModal folder="Houston" onClose={() => {}} /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Untick all' }))
    expect(screen.getByRole('button', { name: 'Award 0 badges' })).toBeDisabled()
  })
})
