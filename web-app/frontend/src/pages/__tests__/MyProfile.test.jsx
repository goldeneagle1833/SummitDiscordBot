import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))

import { useAuth } from '@/context/AuthContext'
import MyProfile from '../MyProfile'

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname + loc.search}</div>
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/me" element={<MyProfile />} />
        <Route path="/me/:panel" element={<MyProfile />} />
        <Route path="/player/:playerId" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('MyProfile deep link', () => {
  const originalLocation = window.location
  beforeEach(() => {
    delete window.location
    window.location = { origin: 'https://sorcererssummit.com', pathname: '/me/block-list', replace: vi.fn() }
  })
  afterEach(() => {
    window.location = originalLocation
  })

  it('sends a logged-in player to their own profile with the block list open', () => {
    useAuth.mockReturnValue({ user: { user_id: '123' }, loading: false })
    renderAt('/me/block-list')
    expect(screen.getByTestId('where').textContent).toBe('/player/123?open=block-list')
  })

  it('opens the plain profile for /me and unknown panels', () => {
    useAuth.mockReturnValue({ user: { user_id: 'google_9' }, loading: false })
    renderAt('/me/nonsense')
    expect(screen.getByTestId('where').textContent).toBe('/player/google_9')
  })

  it('sends a logged-out player to log in and come back', () => {
    useAuth.mockReturnValue({ user: false, loading: false })
    renderAt('/me/block-list')
    expect(window.location.replace).toHaveBeenCalledWith(
      '/login?next=' + encodeURIComponent('https://sorcererssummit.com/me/block-list'),
    )
  })
})
