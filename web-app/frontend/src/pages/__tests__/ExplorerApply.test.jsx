import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent, waitFor } from '@/test/test-utils'

vi.mock('@/api/explorerApplications', () => ({
  submitApplication: vi.fn(),
  getMyApplication: vi.fn(),
}))

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))

import { submitApplication, getMyApplication } from '@/api/explorerApplications'
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
  })

  it('asks anonymous visitors to log in with Discord', async () => {
    useAuth.mockReturnValue({ user: false, loading: false })
    renderWithRouter(<ExplorerApply />)
    expect(
      await screen.findByRole('link', { name: 'Log in with Discord' })
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Submit Application/ })).toBeNull()
  })

  it('tells Google users to switch to Discord', async () => {
    useAuth.mockReturnValue({
      user: { id: 'google_1', username: 'G', auth_provider: 'google' },
      loading: false,
    })
    renderWithRouter(<ExplorerApply />)
    expect(await screen.findByText(/signed in with Google/)).toBeInTheDocument()
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

  it('shows the existing status instead of the form when already applied', async () => {
    getMyApplication.mockResolvedValue({
      application: { id: 1, status: 'pre_approved' },
    })
    renderWithRouter(<ExplorerApply />)
    expect(await screen.findByText(/You have already applied/)).toBeInTheDocument()
    expect(screen.getByText('Pre-approved')).toBeInTheDocument()
    expect(screen.queryByLabelText(/First name/)).toBeNull()
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
