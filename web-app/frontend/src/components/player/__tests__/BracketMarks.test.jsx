import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import BracketMarks, { resetBracketMarksCache } from '../BracketMarks'
import { getBracketMarks } from '@/api/brackets'

vi.mock('@/api/brackets', () => ({
  getBracketMarks: vi.fn(),
}))

const MARKS = {
  u_champ: {
    wins: 1,
    best: 1,
    best_label: 'Champion',
    entries: [{ slug: 'gothic-6', name: 'Gothic Season 6', placement: 1, label: 'Champion' }],
  },
  u_double: {
    wins: 2,
    best: 1,
    best_label: 'Champion',
    entries: [
      { slug: 'a', name: 'Cup A', placement: 1, label: 'Champion' },
      { slug: 'b', name: 'Cup B', placement: 1, label: 'Champion' },
    ],
  },
  u_finalist: {
    wins: 0,
    best: 2,
    best_label: 'Finalist',
    entries: [{ slug: 'a', name: 'Cup A', placement: 2, label: 'Finalist' }],
  },
  u_top4: {
    wins: 0,
    best: 3,
    best_label: 'Top 4',
    entries: [{ slug: 'a', name: 'Cup A', placement: 3, label: 'Top 4' }],
  },
  u_cut: {
    wins: 0,
    best: 9,
    best_label: 'Top cut',
    entries: [{ slug: 'a', name: 'Cup A', placement: 9, label: 'Top cut' }],
  },
}

describe('BracketMarks', () => {
  beforeEach(() => {
    resetBracketMarksCache()
    getBracketMarks.mockClear()
    getBracketMarks.mockResolvedValue({ success: true, marks: MARKS })
  })

  it('draws a yurt for a bracket win', async () => {
    const { container } = renderWithRouter(<BracketMarks playerId="u_champ" />)
    await waitFor(() => expect(container.querySelectorAll('img')).toHaveLength(1))
    expect(container.querySelector('img')).toHaveAttribute('src', '/static/images/favicon.png')
  })

  it('draws one yurt per win', async () => {
    const { container } = renderWithRouter(<BracketMarks playerId="u_double" />)
    await waitFor(() => expect(container.querySelectorAll('img')).toHaveLength(2))
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      '2x bracket winner: Cup A, Cup B',
    )
  })

  it('tags a finalist instead of a yurt', async () => {
    const { container } = renderWithRouter(<BracketMarks playerId="u_finalist" />)
    expect(await screen.findByText('Finalist')).toBeInTheDocument()
    expect(container.querySelectorAll('img')).toHaveLength(0)
  })

  it('tags top 4 and top cut finishes', async () => {
    renderWithRouter(<BracketMarks playerId="u_top4" />)
    expect(await screen.findByText('Top 4')).toBeInTheDocument()

    resetBracketMarksCache(MARKS)
    renderWithRouter(<BracketMarks playerId="u_cut" />)
    expect(await screen.findByText('Top cut')).toBeInTheDocument()
  })

  it('names the bracket behind the tag', async () => {
    renderWithRouter(<BracketMarks playerId="u_finalist" />)
    expect(await screen.findByText('Finalist')).toHaveAttribute('title', 'Finalist — Cup A')
  })

  it('shows nothing for a player with no postseason', async () => {
    const { container } = renderWithRouter(<BracketMarks playerId="u_nobody" />)
    await waitFor(() => expect(getBracketMarks).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('fetches once however many names are on the page', async () => {
    renderWithRouter(
      <>
        <BracketMarks playerId="u_champ" />
        <BracketMarks playerId="u_finalist" />
        <BracketMarks playerId="u_nobody" />
      </>,
    )
    await waitFor(() => expect(screen.getByText('Finalist')).toBeInTheDocument())
    expect(getBracketMarks).toHaveBeenCalledTimes(1)
  })

  it('stays quiet when the marks cannot be loaded', async () => {
    getBracketMarks.mockRejectedValue(new Error('boom'))
    const { container } = renderWithRouter(<BracketMarks playerId="u_champ" />)
    await waitFor(() => expect(getBracketMarks).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
