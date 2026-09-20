import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, render, waitFor } from '@/test/test-utils'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import ExplorerAdminGuard from '../ExplorerAdminGuard'

vi.mock('@/api/auth', () => ({ getMe: vi.fn() }))

import { getMe } from '@/api/auth'

function renderGuarded(mockUser) {
  if (mockUser === null) {
    getMe.mockReturnValue(new Promise(() => {})) // loading forever
  } else if (mockUser === false) {
    getMe.mockRejectedValue(new Error('Unauthorized'))
  } else {
    getMe.mockResolvedValue(mockUser)
  }

  return render(
    <MemoryRouter initialEntries={['/admin/explorer-applications']}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<p>Home page</p>} />
          <Route
            path="/admin/explorer-applications"
            element={
              <ExplorerAdminGuard>
                <p>Explorer admin content</p>
              </ExplorerAdminGuard>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  )
}

describe('ExplorerAdminGuard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows a spinner while auth is loading', () => {
    const { container } = renderGuarded(null)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('redirects unauthenticated visitors home', async () => {
    renderGuarded(false)
    await waitFor(() => expect(screen.getByText('Home page')).toBeInTheDocument())
  })

  it('redirects ordinary players home', async () => {
    renderGuarded({ user_id: '1', username: 'Player', is_admin: false })
    await waitFor(() => expect(screen.getByText('Home page')).toBeInTheDocument())
  })

  it('lets Explorer admins through', async () => {
    renderGuarded({ user_id: '2', username: 'Council', is_explorer_admin: true })
    await waitFor(() =>
      expect(screen.getByText('Explorer admin content')).toBeInTheDocument()
    )
  })

  it('lets global admins through as a superset', async () => {
    renderGuarded({ user_id: '3', username: 'Admin', is_admin: true })
    await waitFor(() =>
      expect(screen.getByText('Explorer admin content')).toBeInTheDocument()
    )
  })
})
