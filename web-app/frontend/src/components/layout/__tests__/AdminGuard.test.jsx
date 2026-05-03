import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, render, waitFor } from '@/test/test-utils'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import AdminGuard from '../AdminGuard'

vi.mock('@/api/auth', () => ({
  getMe: vi.fn(),
}))

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
    <MemoryRouter initialEntries={['/admin/audit-log']}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<p>Home page</p>} />
          <Route
            path="/admin/audit-log"
            element={
              <AdminGuard>
                <p>Admin content</p>
              </AdminGuard>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  )
}

describe('AdminGuard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows spinner while loading', () => {
    const { container } = renderGuarded(null)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('redirects non-admin users to home', async () => {
    renderGuarded({ user_id: '1', username: 'User', is_admin: false })
    await waitFor(() => expect(screen.getByText('Home page')).toBeInTheDocument())
  })

  it('redirects unauthenticated users to home', async () => {
    renderGuarded(false)
    await waitFor(() => expect(screen.getByText('Home page')).toBeInTheDocument())
  })

  it('renders children for admin users', async () => {
    renderGuarded({ user_id: '1', username: 'Admin', is_admin: true })
    await waitFor(() => expect(screen.getByText('Admin content')).toBeInTheDocument())
  })
})
