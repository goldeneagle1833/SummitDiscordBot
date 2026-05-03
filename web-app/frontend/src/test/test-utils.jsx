import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'

/**
 * Renders a component wrapped in MemoryRouter for tests that need routing.
 */
export function renderWithRouter(ui, { route = '/', ...options } = {}) {
  return render(ui, {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    ),
    ...options,
  })
}

/**
 * Renders with both Router and AuthProvider.
 * Mock getMe before using this to control auth state.
 */
export function renderWithProviders(ui, { route = '/', ...options } = {}) {
  return render(ui, {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>{children}</AuthProvider>
      </MemoryRouter>
    ),
    ...options,
  })
}

export { render, screen, within, waitFor, act } from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
