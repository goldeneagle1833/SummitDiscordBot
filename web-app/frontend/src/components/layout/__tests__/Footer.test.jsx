import { describe, it, expect } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import Footer from '../Footer'

describe('Footer', () => {
  it('renders the brand name', () => {
    renderWithRouter(<Footer />)
    expect(screen.getByText('Sorcerers Summit')).toBeInTheDocument()
  })

  it('renders navigation links', () => {
    renderWithRouter(<Footer />)
    expect(screen.getByRole('link', { name: /about/i })).toHaveAttribute('href', '/about')
    expect(screen.getByRole('link', { name: /help/i })).toHaveAttribute('href', '/help')
    expect(screen.getByRole('link', { name: /community/i })).toHaveAttribute('href', '/community')
  })

  it('renders legal links', () => {
    renderWithRouter(<Footer />)
    expect(screen.getByRole('link', { name: /privacy policy/i })).toHaveAttribute('href', '/privacy')
    expect(screen.getByRole('link', { name: /terms of service/i })).toHaveAttribute('href', '/terms')
  })

  it('displays the current year in copyright', () => {
    renderWithRouter(<Footer />)
    const year = new Date().getFullYear().toString()
    expect(screen.getByText(new RegExp(year))).toBeInTheDocument()
  })
})
