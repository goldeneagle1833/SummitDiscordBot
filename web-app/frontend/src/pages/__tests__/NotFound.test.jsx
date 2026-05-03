import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import NotFound from '../NotFound'

describe('NotFound page', () => {
  it('renders 404 heading', () => {
    renderWithRouter(<NotFound />)
    expect(screen.getByText('404')).toBeInTheDocument()
  })

  it('renders "Page not found" message', () => {
    renderWithRouter(<NotFound />)
    expect(screen.getByText(/page not found/i)).toBeInTheDocument()
  })

  it('renders a link back to home', () => {
    renderWithRouter(<NotFound />)
    const link = screen.getByRole('link', { name: /back to home/i })
    expect(link).toHaveAttribute('href', '/')
  })

  it('sets the page title', () => {
    renderWithRouter(<NotFound />)
    expect(document.title).toBe('404 Not Found | Sorcerers Summit')
  })
})
