import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import Top8Profile from '../Top8Profile'

vi.mock('@/api/paperFinishes', () => ({ assignPaperResult: vi.fn(), clearPaperResult: vi.fn(), getPaperFinishes: vi.fn() }))

const MATCHED = { place: 1, deck_id: 'd1', status: 'auto', player: { user_id: '42', name: 'Avaloneer' } }

describe('Top8Profile', () => {
  it('links a matched entry to its Summit profile', () => {
    renderWithRouter(<Top8Profile entry={MATCHED} deckId="d1" folder="LinCon" />)
    expect(screen.getByRole('link', { name: /Avaloneer/ })).toHaveAttribute('href', '/player/42')
    expect(screen.queryByText('Change')).not.toBeInTheDocument()
  })

  it('shows nothing to visitors when unmatched', () => {
    const { container } = renderWithRouter(<Top8Profile entry={{ status: 'unmatched', player: null }} deckId="d1" folder="LinCon" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('gives admins a way to set or change the profile', () => {
    renderWithRouter(<Top8Profile entry={{ status: 'unmatched', player: null }} deckId="d1" folder="LinCon" isAdmin />)
    expect(screen.getByText('Set profile')).toBeInTheDocument()
    renderWithRouter(<Top8Profile entry={MATCHED} deckId="d1" folder="LinCon" isAdmin />)
    expect(screen.getByText('Change')).toBeInTheDocument()
    expect(screen.getByText('Not them')).toBeInTheDocument()
  })
})
