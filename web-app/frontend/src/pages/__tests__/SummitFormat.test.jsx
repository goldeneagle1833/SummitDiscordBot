import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter } from '@/test/test-utils'
import { getProducts } from '@/api/store'
import SummitFormat, { findSeasonTicket } from '../SummitFormat'

vi.mock('@/api/store', async () => {
  const actual = await vi.importActual('@/api/store')
  return { ...actual, getProducts: vi.fn() }
})

const product = (id, name, price_cents, extra = {}) => ({ id, name, price_cents, currency: 'USD', ...extra })

beforeEach(() => {
  getProducts.mockResolvedValue({ products: [] })
})

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

  it('shows placeholders when no ticket is in the store', async () => {
    renderWithRouter(<SummitFormat />)
    expect(await screen.findAllByText(/details coming soon/i)).not.toHaveLength(0)
    expect(screen.queryByRole('link', { name: /get a ticket/i })).not.toBeInTheDocument()
  })

  it('fills price and where to buy from the Season ticket listing', async () => {
    getProducts.mockResolvedValue({
      products: [
        product(1, 'Island Leviathan Pack', 599),
        product(2, 'Season 9 Ticket', 2500, { description: 'One entry for Season 9.' }),
      ],
    })
    renderWithRouter(<SummitFormat />)
    expect(await screen.findByText('Season 9 Ticket')).toBeInTheDocument()
    expect(screen.getAllByText('$25.00').length).toBeGreaterThan(0)
    expect(screen.getByText('One entry for Season 9.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /get a ticket/i })).toHaveAttribute('href', '/store')
    expect(screen.getByRole('link', { name: /the summit store/i })).toHaveAttribute('href', '/store')
  })

  it('picks the newest season ticket', () => {
    const found = findSeasonTicket([product(1, 'Season 8 Ticket', 2000), product(2, 'Season 9 ticket', 2500), product(3, 'T-shirt', 1500)])
    expect(found.season).toBe(9)
    expect(found.product.id).toBe(2)
    expect(findSeasonTicket([product(3, 'T-shirt', 1500)])).toBeNull()
  })
})
