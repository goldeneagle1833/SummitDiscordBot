import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent, waitFor, within } from '@/test/test-utils'

vi.mock('@/api/explorerApplications', () => ({
  getApplications: vi.fn(),
  getApplication: vi.fn(),
  voteOnApplication: vi.fn(),
  setApplicationStatus: vi.fn(),
  addApplicationComment: vi.fn(),
  addCandidate: vi.fn(),
  deleteApplication: vi.fn(),
  regeocodeApplication: vi.fn(),
  EXPORT_CSV_URL: '/api/explorer/applications/export.csv',
}))

// Leaflet needs a real DOM with layout; jsdom has neither.
vi.mock('@/components/explorer/ApplicationsMap', () => ({
  default: ({ applications }) => (
    <div data-testid="map">{applications.length} pins available</div>
  ),
}))

vi.mock('@/context/AuthContext', () => ({
  useAuth: vi.fn(() => ({ user: { id: 'admin_user_1', is_admin: true }, loading: false })),
}))

import {
  getApplications,
  getApplication,
  voteOnApplication,
  setApplicationStatus,
  addApplicationComment,
  addCandidate,
  regeocodeApplication,
} from '@/api/explorerApplications'
import ExplorerApplications from '../ExplorerApplications'

const application = {
  id: 1,
  first_name: 'Ruben',
  last_name: 'Sanchez',
  discord_handle: 'Rubonic',
  city: 'Mechanicsville',
  state: 'Virginia',
  lgs_name: 'Waterloo Games',
  status: 'pending',
  source: 'application',
  latitude: 37.6,
  longitude: -77.4,
  vote_count: 1,
  comment_count: 0,
  average_score: 4,
}

const unmapped = {
  id: 2,
  first_name: 'Kevin',
  last_name: 'Rodriguez',
  discord_handle: 'Kevmo',
  city: '',
  state: 'PNW',
  status: 'pending',
  source: 'admin_added',
  created_by: 'AdminUser',
  latitude: null,
  longitude: null,
  vote_count: 0,
  comment_count: 0,
  average_score: null,
}

const detail = {
  application,
  votes: [
    {
      id: 10,
      voter_user_id: 'admin_user_1',
      voter_name: 'AdminUser',
      enthusiasm: 4,
      track_record: 4,
      local_activity: 4,
    },
  ],
  comments: [],
}

describe('ExplorerApplications admin page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getApplications.mockResolvedValue({ applications: [application, unmapped] })
    getApplication.mockResolvedValue(detail)
    voteOnApplication.mockResolvedValue({ votes: detail.votes })
    setApplicationStatus.mockResolvedValue({ status: 'approved' })
    addApplicationComment.mockResolvedValue({ comments: [] })
    addCandidate.mockResolvedValue({ application_id: 3 })
    regeocodeApplication.mockResolvedValue({ latitude: 1, longitude: 2 })
  })

  it('shows a card per application with its score', async () => {
    renderWithRouter(<ExplorerApplications />)
    expect(await screen.findByText('Ruben Sanchez')).toBeInTheDocument()
    expect(screen.getByText('Kevin Rodriguez')).toBeInTheDocument()
    expect(screen.getByText('4 / 5')).toBeInTheDocument()
    expect(screen.getByText('Unscored')).toBeInTheDocument()
  })

  it('passes applications to the map and flags the unmapped ones', async () => {
    renderWithRouter(<ExplorerApplications />)
    // The map mounts before the fetch resolves, so wait for the loaded list.
    await waitFor(() =>
      expect(screen.getByTestId('map')).toHaveTextContent('2 pins available')
    )
    expect(
      screen.getByText(/1 application could not be placed on the map/)
    ).toBeInTheDocument()
  })

  it('marks hand-added candidates', async () => {
    renderWithRouter(<ExplorerApplications />)
    expect(await screen.findByText('Added by AdminUser')).toBeInTheDocument()
  })

  it('filters by status', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await screen.findByText('Ruben Sanchez')

    await user.selectOptions(screen.getByLabelText('Filter by status'), 'approved')

    await waitFor(() => expect(getApplications).toHaveBeenLastCalledWith('approved'))
  })

  it('opens the detail dialog with the full application', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await user.click(await screen.findByText('Ruben Sanchez'))

    const dialog = await screen.findByRole('dialog', { name: 'Application detail' })
    expect(within(dialog).getByText('Waterloo Games')).toBeInTheDocument()
    expect(within(dialog).getByText('Mechanicsville, Virginia')).toBeInTheDocument()
  })

  it('prefills the reviewer’s existing scores', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await user.click(await screen.findByText('Ruben Sanchez'))

    const dialog = await screen.findByRole('dialog', { name: 'Application detail' })
    expect(within(dialog).getByLabelText('Enthusiasm')).toHaveValue('4')
  })

  it('saves scores for the open application', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await user.click(await screen.findByText('Ruben Sanchez'))

    const dialog = await screen.findByRole('dialog', { name: 'Application detail' })
    await user.selectOptions(within(dialog).getByLabelText('Enthusiasm'), '5')
    await user.click(within(dialog).getByRole('button', { name: 'Save scores' }))

    await waitFor(() =>
      expect(voteOnApplication).toHaveBeenCalledWith(1, {
        enthusiasm: 5,
        track_record: 4,
        local_activity: 4,
      })
    )
  })

  it('changes the application status', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await user.click(await screen.findByText('Ruben Sanchez'))

    const dialog = await screen.findByRole('dialog', { name: 'Application detail' })
    await user.click(within(dialog).getByRole('button', { name: 'Approved' }))

    await waitFor(() => expect(setApplicationStatus).toHaveBeenCalledWith(1, 'approved'))
  })

  it('adds a note', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await user.click(await screen.findByText('Ruben Sanchez'))

    const dialog = await screen.findByRole('dialog', { name: 'Application detail' })
    await user.type(within(dialog).getByLabelText('Add a note'), 'Spoke with the owner')
    await user.click(within(dialog).getByRole('button', { name: 'Add note' }))

    await waitFor(() =>
      expect(addApplicationComment).toHaveBeenCalledWith(1, 'Spoke with the owner')
    )
  })

  it('offers a geocode retry only when the pin is missing', async () => {
    getApplication.mockResolvedValue({ ...detail, application: unmapped })
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await user.click(await screen.findByText('Kevin Rodriguez'))

    const dialog = await screen.findByRole('dialog', { name: 'Application detail' })
    await user.click(within(dialog).getByRole('button', { name: 'Find on map' }))

    await waitFor(() => expect(regeocodeApplication).toHaveBeenCalledWith(2))
  })

  it('adds a candidate by Discord handle', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ExplorerApplications />)
    await screen.findByText('Ruben Sanchez')

    await user.click(screen.getByRole('button', { name: '+ Add Candidate' }))
    await user.type(screen.getByLabelText('Discord handle'), 'Kevmo')
    await user.click(screen.getByRole('button', { name: 'Add Candidate' }))

    await waitFor(() =>
      expect(addCandidate).toHaveBeenCalledWith(
        expect.objectContaining({ discord_handle: 'Kevmo' })
      )
    )
    expect(getApplications).toHaveBeenCalledTimes(2)
  })

  it('links to the CSV export', async () => {
    renderWithRouter(<ExplorerApplications />)
    const link = await screen.findByRole('link', { name: 'Export CSV' })
    expect(link).toHaveAttribute('href', '/api/explorer/applications/export.csv')
  })

  it('shows an error if loading fails', async () => {
    getApplications.mockRejectedValue(new Error('nope'))
    renderWithRouter(<ExplorerApplications />)
    expect(await screen.findByText('nope')).toBeInTheDocument()
  })
})
