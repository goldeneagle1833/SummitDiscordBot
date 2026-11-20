import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import SummitFormat from '../SummitFormat'

describe('Summit format page', () => {
  it('renders the heading and the main sections', () => {
    renderWithRouter(<SummitFormat />)
    expect(screen.getByText(/how the sorcerers summit works/i)).toBeInTheDocument()
    for (const name of ['Tickets', 'Top cut', 'Prizes', 'FAQ']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    }
  })

  it('describes the top 32 cut and seeding', () => {
    renderWithRouter(<SummitFormat />)
    expect(screen.getAllByText(/top 32 ticket holders/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/seeds 9 to 32 are drawn at random/i)).toBeInTheDocument()
  })

  it('links to the Season Top Cut page', () => {
    renderWithRouter(<SummitFormat />)
    expect(screen.getByRole('link', { name: /season top cut/i })).toHaveAttribute('href', '/brackets')
  })

  it('sets the page title', () => {
    renderWithRouter(<SummitFormat />)
    expect(document.title).toBe('Summit Format | Sorcerers Summit')
  })
})
