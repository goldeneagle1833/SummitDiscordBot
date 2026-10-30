import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { PaperFinishBadge, PaperFinishesSection, resetPaperFinishesCache } from '../PaperFinishes'

vi.mock('@/api/paperFinishes', () => ({ getPaperFinishes: vi.fn() }))

const FINISHES = [
  { folder: 'SCG Con Alanta 2026', event: 'SCG Con Atlanta', label: 'Winner', place: 1, avatar: 'Druid', event_date_display: 'Mar 2026', title: 'Winner · SCG Con Atlanta' },
  { folder: 'LinCon May 14-16 2026', event: 'LinCon', label: 'Top 8', place: 6, avatar: 'Imposter', title: 'Top 8 · LinCon' },
]

describe('PaperFinishes', () => {
  beforeEach(() => resetPaperFinishesCache())

  it('shows the best finish on the badge with a count of the rest', () => {
    renderWithRouter(<PaperFinishBadge finishes={FINISHES} />)
    expect(screen.getByText('Winner')).toBeInTheDocument()
    expect(screen.getByText('SCG Con Atlanta')).toBeInTheDocument()
    expect(screen.getByText('+1')).toBeInTheDocument()
  })

  it('renders nothing without finishes', () => {
    const { container } = renderWithRouter(<PaperFinishBadge finishes={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('lists every finish with a link to its event', () => {
    renderWithRouter(<PaperFinishesSection finishes={FINISHES} />)
    expect(screen.getByText('Paper tournament finishes')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'LinCon' })).toHaveAttribute('href', '/top-8/LinCon%20May%2014-16%202026')
    expect(screen.getByText('Druid · Mar 2026')).toBeInTheDocument()
  })
})
