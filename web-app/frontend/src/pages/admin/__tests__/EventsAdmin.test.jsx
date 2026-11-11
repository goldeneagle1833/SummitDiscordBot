import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import * as api from '@/api/preconAdmin'
import EventsAdmin from '../EventsAdmin'

const LIMITS = { min_ranked_games: { min: 1, max: 50 }, season_days: { min: 1, max: 120 } }
const SETTINGS = { queue_enabled: false, min_ranked_games: 5, block_rematch: true, season_days: 28 }
const live = {
  season_id: 1, name: 'LM vs FM 1', starts_at: '2026-11-12T18:00:00', ends_at: '2026-12-10T18:00:00',
  starts_at_iso: '2026-11-12T18:00:00+00:00', ends_at_iso: '2099-12-10T18:00:00+00:00',
  last_day_iso: '2099-12-10T18:00:00+00:00', ended_at: null, is_open: true, games: 3, players: 2,
}

vi.mock('@/api/players', () => ({ searchPlayers: vi.fn(() => Promise.resolve({ players: [] })) }))
vi.mock('@/api/preconAdmin', () => ({
  getPreconAdmin: vi.fn(),
  updatePreconSettings: vi.fn(),
  startPreconSeason: vi.fn(),
  updatePreconSeason: vi.fn(),
  endPreconSeason: vi.fn(),
  reportPreconMatch: vi.fn(),
  removePreconMatch: vi.fn(),
}))

const empty = { settings: SETTINGS, limits: LIMITS, seasons: [], current_season_id: null, open_season_id: null, recent: [] }

describe('EventsAdmin', () => {
  beforeEach(() => vi.clearAllMocks())

  it('starts a ladder and switches the queue on with it', async () => {
    api.getPreconAdmin.mockResolvedValue(empty)
    api.startPreconSeason.mockResolvedValue({
      ...empty, settings: { ...SETTINGS, queue_enabled: true }, seasons: [live], current_season_id: 1, open_season_id: 1,
    })
    renderWithRouter(<EventsAdmin />)
    expect(await screen.findByText('Start a ladder')).toBeInTheDocument()
    expect(screen.getByText(/Switched off\. Players don't see/)).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText('LM vs FM Ladder 1'), { target: { value: 'LM vs FM 1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start ladder' }))
    await waitFor(() => expect(api.startPreconSeason).toHaveBeenCalledWith({
      name: 'LM vs FM 1', days: 28, starts_at: null, open_queue: true,
    }))
    expect(await screen.findByText('Running now')).toBeInTheDocument()
    expect(screen.getByText(/Players can join/)).toBeInTheDocument()
  })

  it('flips the queue switch and saves the rules', async () => {
    api.getPreconAdmin.mockResolvedValue({ ...empty, seasons: [live], current_season_id: 1, open_season_id: 1 })
    api.updatePreconSettings.mockImplementation((changes) => Promise.resolve({
      ...empty, seasons: [live], current_season_id: 1, open_season_id: 1,
      settings: { ...SETTINGS, ...changes }, bot_refreshed: false,
    }))
    renderWithRouter(<EventsAdmin />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Precon queue on or off' }))
    await waitFor(() => expect(api.updatePreconSettings).toHaveBeenCalledWith({ queue_enabled: true }))
    expect(await screen.findByText(/Discord picks it up within a minute/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Games to be ranked'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save rules' }))
    await waitFor(() => expect(api.updatePreconSettings).toHaveBeenLastCalledWith({
      min_ranked_games: 3, block_rematch: true, season_days: 28,
    }))
  })

  it('shows a server error', async () => {
    api.getPreconAdmin.mockResolvedValue({ ...empty, seasons: [live], current_season_id: 1, open_season_id: 1 })
    api.endPreconSeason.mockRejectedValue(new Error('No precon ladder is running'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithRouter(<EventsAdmin />)
    fireEvent.click(await screen.findByRole('button', { name: 'End ladder now' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No precon ladder is running')
  })
})

describe('EventsAdmin PSO test mode', () => {
  it('switches test mode on', async () => {
    api.getPreconAdmin.mockResolvedValue({ ...empty, settings: { ...SETTINGS, pso_test_mode: false } })
    api.updatePreconSettings.mockImplementation((changes) => Promise.resolve({
      ...empty, settings: { ...SETTINGS, pso_test_mode: false, ...changes },
    }))
    renderWithRouter(<EventsAdmin />)
    fireEvent.click(await screen.findByRole('switch', { name: 'PSO test mode on or off' }))
    await waitFor(() => expect(api.updatePreconSettings).toHaveBeenCalledWith({ pso_test_mode: true }))
    expect(await screen.findByText(/get 200 answers with sample data/)).toBeInTheDocument()
  })
})
