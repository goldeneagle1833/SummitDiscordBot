import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Routes, Route } from 'react-router-dom'
import { renderWithRouter } from '@/test/test-utils'
import PlayerAvatar from '../PlayerAvatar'

vi.mock('@/api/client', () => ({
  get: vi.fn(() => Promise.resolve({
    events: [
      { event_id: 8, event_name: 'Season 8', is_active: true },
      { event_id: 7, event_name: 'Season 7', is_active: false },
    ],
  })),
}))

vi.mock('@/api/players', () => ({
  getPlayerAvatarStats: vi.fn((id, name, { event } = {}) => Promise.resolve({
    player_name: 'Hicham',
    avatar: name,
    wins: event === '7' ? 1 : 5,
    losses: 2,
    total: event === '7' ? 3 : 7,
    win_rate: 50,
    matchups: [],
    matches: [],
  })),
}))

import { getPlayerAvatarStats } from '@/api/players'

function renderAt(path) {
  return renderWithRouter(
    <Routes>
      <Route path="/player/:playerId/avatar/:avatarName" element={<PlayerAvatar />} />
    </Routes>,
    { route: path },
  )
}

beforeEach(() => vi.clearAllMocks())

describe('PlayerAvatar period picker', () => {
  it('opens on the period in the link and lists past events only', async () => {
    renderAt('/player/1/avatar/Pathfinder?event=current')
    const picker = await screen.findByLabelText('Period')
    expect(picker).toHaveValue('current')
    expect(getPlayerAvatarStats).toHaveBeenLastCalledWith('1', 'Pathfinder', { event: 'current' })
    expect(await screen.findByRole('option', { name: 'Season 7' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Season 8' })).not.toBeInTheDocument()
  })

  it('reloads the stats for the chosen event', async () => {
    renderAt('/player/1/avatar/Pathfinder')
    const picker = await screen.findByLabelText('Period')
    expect(picker).toHaveValue('lifetime')
    await screen.findByRole('option', { name: 'Season 7' })
    await userEvent.selectOptions(picker, '7')
    expect(getPlayerAvatarStats).toHaveBeenLastCalledWith('1', 'Pathfinder', { event: '7' })
    expect(await screen.findByText('3')).toBeInTheDocument()
  })
})
