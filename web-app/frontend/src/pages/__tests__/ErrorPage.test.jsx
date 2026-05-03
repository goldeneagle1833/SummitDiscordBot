import { describe, it, expect } from 'vitest'
import { screen, render } from '@/test/test-utils'
import { MemoryRouter } from 'react-router-dom'
import ErrorPage from '../ErrorPage'

function renderError(search = '') {
  return render(
    <MemoryRouter initialEntries={[`/error${search}`]}>
      <ErrorPage />
    </MemoryRouter>
  )
}

describe('ErrorPage', () => {
  it('shows default error code and message', () => {
    renderError()
    expect(screen.getByText('Error')).toBeInTheDocument()
    expect(screen.getByText(/unexpected error/i)).toBeInTheDocument()
  })

  it('shows custom code and message from search params', () => {
    renderError('?code=403&message=Access%20denied')
    expect(screen.getByText('403')).toBeInTheDocument()
    expect(screen.getByText('Access denied')).toBeInTheDocument()
  })

  it('renders a link back to home', () => {
    renderError()
    const link = screen.getByRole('link', { name: /back to home/i })
    expect(link).toHaveAttribute('href', '/')
  })
})
