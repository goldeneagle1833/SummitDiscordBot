import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import About from '../About'

describe('About page', () => {
  it('renders the page heading', () => {
    renderWithRouter(<About />)
    expect(screen.getByText(/about sorcerers summit/i)).toBeInTheDocument()
  })

  it('renders description content', () => {
    renderWithRouter(<About />)
    expect(screen.getByText(/community-driven platform/i)).toBeInTheDocument()
  })

  it('mentions the Discord bot', () => {
    renderWithRouter(<About />)
    expect(screen.getByText(/discord bot/i)).toBeInTheDocument()
  })

  it('sets the page title', () => {
    renderWithRouter(<About />)
    expect(document.title).toBe('About | Sorcerers Summit')
  })
})
