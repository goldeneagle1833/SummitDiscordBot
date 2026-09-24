import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent, waitFor } from '@/test/test-utils'

vi.mock('@/api/explorerApplications', () => ({
  submitApplication: vi.fn(),
  getMyApplication: vi.fn(),
  updateMyApplication: vi.fn(),
}))

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))

import {
  submitApplication,
  getMyApplication,
  updateMyApplication,
} from '@/api/explorerApplications'
import { useAuth } from '@/context/AuthContext'
import ExplorerApply from '../ExplorerApply'

const discordUser = { id: '555', username: 'Rubonic', auth_provider: 'discord' }

async function fillRequiredFields(user) {
  await user.type(screen.getByLabelText(/First name/), 'Ruben')
  await user.type(screen.getByLabelText(/Last name/), 'Sanchez')
  await user.type(screen.getByLabelText(/Email address/), 'rubonic@example.com')
  await user.type(screen.getByLabelText(/City or town/), 'Mechanicsville')
  await user.type(screen.getByLabelText(/State or province/), 'Virginia')
  await user.type(screen.getByLabelText(/Name of the LGS/), 'Waterloo Games')
  await user.click(screen.getByRole('checkbox'))
}

describe('ExplorerApply page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue({ user: discordUser, loading: false })
    getMyApplication.mockResolvedValue({ application: null })
    submitApplication.mockResolvedValue({ application_id: 1 })
    updateMyApplication.mockResolvedValue({ application: { id: 1, status: 'pending' } })
  })

  it('asks anonymous visitors to log in with Discord', async () => {
    useAuth.mockReturnValue({ user: false, loading: false })
    renderWithRouter(<ExplorerApply />)
    expect(
      await screen.findByRole('link', { name: 'Log in with Discord' })
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Submit Application/ })).toBeNull()
  })

  it('lets Google users apply too', async () => {
    useAuth.mockReturnValue({
      user: { id: 'google_1', username: 'Some Googler', auth_provider: 'google' },
      loading: false,
    })
    renderWithRouter(<ExplorerApply />)
    expect(await screen.findByLabelText(/First name/)).toBeInTheDocument()
  })

  it('does not guess a Discord handle for a Google user', async () => {
    useAuth.mockReturnValue({
      user: { id: 'google_1', username: 'Some Googler', auth_provider: 'google' },
      loading: false,
    })
    renderWithRouter(<ExplorerApply />)
    // Their Google display name is not their Discord handle, so leave it blank.
    expect(await screen.findByLabelText(/Discord handle/)).toHaveValue('')
  })

  it('prefills the Discord handle from the session', async () => {
    renderWithRouter(<ExplorerApply />)
    await waitFor(() =>
      expect(screen.getByLabelText(/Discord handle/)).toHaveValue('Rubonic')
    )
  })

  it('submits the application and confirms', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApply />)
    await screen.findByLabelText(/First name/)

    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: /Submit Application/ }))

    await waitFor(() => expect(submitApplication).toHaveBeenCalled())
    const payload = submitApplication.mock.calls[0][0]
    expect(payload).toMatchObject({
      first_name: 'Ruben',
      last_name: 'Sanchez',
      email: 'rubonic@example.com',
      city: 'Mechanicsville',
      state: 'Virginia',
      lgs_name: 'Waterloo Games',
      read_navigator_role: true,
    })
    expect(await screen.findByText(/your application is in/)).toBeInTheDocument()
  })

  it('reopens the answers for editing when an application is still open', async () => {
    getMyApplication.mockResolvedValue({
      application: {
        id: 1, status: 'pending', editable: true, first_name: 'Ruben', city: 'Mechanicsville',
      },
    })
    renderWithRouter(<ExplorerApply />)

    expect(await screen.findByText(/You have already applied/)).toBeInTheDocument()
    // Prefilled from what they sent, not a blank form.
    await waitFor(() => expect(screen.getByLabelText(/First name/)).toHaveValue('Ruben'))
    expect(screen.getByLabelText(/City or town/)).toHaveValue('Mechanicsville')
    expect(screen.getByRole('button', { name: /Update Application/ })).toBeInTheDocument()
  })

  it('saves an edit through the update endpoint', async () => {
    getMyApplication.mockResolvedValue({
      application: {
        id: 1, status: 'pending', first_name: 'Ruben', last_name: 'Sanchez',
        email: 'r@example.com', city: 'Mechanicsville', state: 'Virginia',
        lgs_name: 'Waterloo Games', read_navigator_role: true,
      },
    })
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApply />)

    const city = await screen.findByLabelText(/City or town/)
    // Wait for the prefill to land before editing, or it overwrites the change.
    await waitFor(() => expect(city).toHaveValue('Mechanicsville'))
    await user.clear(city)
    await user.type(city, 'Richmond')
    await user.click(screen.getByRole('button', { name: /Update Application/ }))

    await waitFor(() => expect(updateMyApplication).toHaveBeenCalled())
    expect(updateMyApplication.mock.calls[0][0].city).toBe('Richmond')
    expect(submitApplication).not.toHaveBeenCalled()
    expect(await screen.findByText(/application has been updated/)).toBeInTheDocument()
  })

  it('shows a published decision read-only', async () => {
    getMyApplication.mockResolvedValue({
      application: { id: 1, status: 'approved', editable: false, first_name: 'Ruben' },
    })
    renderWithRouter(<ExplorerApply />)

    expect(await screen.findByText(/has made its decision/)).toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
    expect(screen.getByText(/Congratulations/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/First name/)).toBeNull()
  })

  it('shows a rejection kindly', async () => {
    getMyApplication.mockResolvedValue({
      application: { id: 1, status: 'rejected', editable: false, first_name: 'Ruben' },
    })
    renderWithRouter(<ExplorerApply />)

    expect(await screen.findByText('Not accepted')).toBeInTheDocument()
    expect(screen.getByText(/weren't able to accept/)).toBeInTheDocument()
  })

  it('surfaces a submission error', async () => {
    submitApplication.mockRejectedValue(new Error('Missing required field(s): city'))
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApply />)
    await screen.findByLabelText(/First name/)

    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: /Submit Application/ }))

    expect(
      await screen.findByText('Missing required field(s): city')
    ).toBeInTheDocument()
  })
})
