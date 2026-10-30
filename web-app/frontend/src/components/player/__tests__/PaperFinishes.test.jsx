import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { PaperFinishChips, PaperFinishesSection, resetPaperFinishesCache } from '../PaperFinishes'

vi.mock('@/api/paperFinishes', () => ({ getPaperFinishes: vi.fn() }))

const FINISHES = [
  { folder: 'SCG Con Alanta 2026', event: 'SCG Con Atlanta', label: 'Winner', place: 1, avatar: 'Druid', event_date_display: 'Mar 2026', title: 'Winner · SCG Con Atlanta' },
  { folder: 'LinCon May 14-16 2026', event: 'LinCon', label: 'Top 8', place: 6, avatar: 'Imposter', title: 'Top 8 · LinCon' },
]

describe('PaperFinishes', () => {
  beforeEach(() => resetPaperFinishesCache())

  it('shows a chip for every finish, each linking to its event', () => {
    renderWithRouter(<PaperFinishChips finishes={FINISHES} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute('href', '/top-8/SCG%20Con%20Alanta%202026')
    expect(screen.getByText('Top 8')).toBeInTheDocument()
    expect(screen.queryByText('+1')).not.toBeInTheDocument()
  })

  it('renders nothing without finishes', () => {
    const { container } = renderWithRouter(<PaperFinishChips finishes={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('lists every finish with a link to its event', () => {
    renderWithRouter(<PaperFinishesSection finishes={FINISHES} />)
    expect(screen.getByText('Paper tournament finishes')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'LinCon' })).toHaveAttribute('href', '/top-8/LinCon%20May%2014-16%202026')
    expect(screen.getByText('Druid · Mar 2026')).toBeInTheDocument()
  })
})
