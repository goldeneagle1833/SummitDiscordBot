import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent, waitFor } from '@/test/test-utils'

vi.mock('@/api/admin', () => ({
  getUserProfiles: vi.fn(),
  getUserProfileCandidates: vi.fn(),
  addUserProfile: vi.fn(),
  deleteUserProfile: vi.fn(),
}))

import {
  getUserProfiles,
  getUserProfileCandidates,
  addUserProfile,
  deleteUserProfile,
} from '@/api/admin'
import UserProfiles from '../UserProfiles'

const manualProfile = {
  user_id: '222222222222222222',
  provider: 'discord',
  display_name: 'Placeholder',
  avatar: null,
  last_login_at: '2026-09-01T00:00:00Z',
  manually_added_by: 'AdminUser',
  manually_added_at: '2026-09-01T00:00:00Z',
  manually_added: true,
  has_logged_in: false,
}

const realProfile = {
  user_id: '111111111111111111',
  provider: 'discord',
  display_name: 'RealUser',
  avatar: null,
  last_login_at: '2026-09-10T00:00:00Z',
  manually_added_by: null,
  manually_added_at: null,
  manually_added: false,
  has_logged_in: true,
}

describe('UserProfiles admin page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getUserProfiles.mockResolvedValue({ profiles: [manualProfile, realProfile], total: 2 })
    getUserProfileCandidates.mockResolvedValue({ candidates: [] })
    addUserProfile.mockResolvedValue({ profile: { display_name: 'GhostPlayer' } })
    deleteUserProfile.mockResolvedValue({ success: true })
  })

  it('lists existing profiles with their total', async () => {
    renderWithRouter(<UserProfiles />)
    expect(await screen.findByText('Placeholder')).toBeInTheDocument()
    expect(screen.getByText('RealUser')).toBeInTheDocument()
    expect(screen.getByText('(2)')).toBeInTheDocument()
  })

  it('only offers Remove for manually added profiles that never logged in', async () => {
    renderWithRouter(<UserProfiles />)
    await screen.findByText('Placeholder')
    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(1)
    expect(screen.getByText(/Added by AdminUser/)).toBeInTheDocument()
  })

  it('looks up known players as you type a Discord name', async () => {
    getUserProfileCandidates.mockResolvedValue({
      candidates: [
        { user_id: '333333333333333333', display_name: 'GhostPlayer', source: 'match history' },
      ],
    })
    const user = userEvent.setup()
    renderWithRouter(<UserProfiles />)
    await screen.findByText('Placeholder')

    await user.type(screen.getByLabelText('Discord name'), 'Ghost')

    expect(await screen.findByText('GhostPlayer')).toBeInTheDocument()
    await waitFor(() => expect(getUserProfileCandidates).toHaveBeenCalledWith('Ghost'))
  })

  it('fills in the Discord ID when a candidate is chosen', async () => {
    getUserProfileCandidates.mockResolvedValue({
      candidates: [
        { user_id: '333333333333333333', display_name: 'GhostPlayer', source: 'match history' },
      ],
    })
    const user = userEvent.setup()
    renderWithRouter(<UserProfiles />)
    await screen.findByText('Placeholder')

    await user.type(screen.getByLabelText('Discord name'), 'Ghost')
    await user.click(await screen.findByRole('button', { name: 'Use' }))

    expect(screen.getByLabelText('Discord user ID')).toHaveValue('333333333333333333')
    expect(screen.getByLabelText('Discord name')).toHaveValue('GhostPlayer')
  })

  it('rejects a non-numeric Discord ID before submitting', async () => {
    const user = userEvent.setup()
    renderWithRouter(<UserProfiles />)
    await screen.findByText('Placeholder')

    await user.type(screen.getByLabelText('Discord name'), 'Someone')
    await user.type(screen.getByLabelText('Discord user ID'), 'abc')

    expect(screen.getByText(/Must be a numeric Discord ID/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add User' })).toBeDisabled()
    expect(addUserProfile).not.toHaveBeenCalled()
  })

  it('submits a new profile and reloads the list', async () => {
    const user = userEvent.setup()
    renderWithRouter(<UserProfiles />)
    await screen.findByText('Placeholder')

    await user.type(screen.getByLabelText('Discord name'), 'GhostPlayer')
    await user.type(screen.getByLabelText('Discord user ID'), '333333333333333333')
    await user.click(screen.getByRole('button', { name: 'Add User' }))

    await waitFor(() =>
      expect(addUserProfile).toHaveBeenCalledWith('333333333333333333', 'GhostPlayer', null)
    )
    expect(await screen.findByText('Added GhostPlayer')).toBeInTheDocument()
    expect(getUserProfiles).toHaveBeenCalledTimes(2)
  })

  it('surfaces a server error when the add fails', async () => {
    addUserProfile.mockRejectedValue(new Error('A profile already exists for 333'))
    const user = userEvent.setup()
    renderWithRouter(<UserProfiles />)
    await screen.findByText('Placeholder')

    await user.type(screen.getByLabelText('Discord name'), 'GhostPlayer')
    await user.type(screen.getByLabelText('Discord user ID'), '333333333333333333')
    await user.click(screen.getByRole('button', { name: 'Add User' }))

    expect(await screen.findByText('A profile already exists for 333')).toBeInTheDocument()
  })

  it('removes a manually added profile after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderWithRouter(<UserProfiles />)
    await screen.findByText('Placeholder')

    await user.click(screen.getByRole('button', { name: 'Remove' }))

    await waitFor(() =>
      expect(deleteUserProfile).toHaveBeenCalledWith('222222222222222222')
    )
  })

  it('shows an error when loading fails', async () => {
    getUserProfiles.mockRejectedValue(new Error('boom'))
    renderWithRouter(<UserProfiles />)
    expect(await screen.findByText('boom')).toBeInTheDocument()
  })
})
