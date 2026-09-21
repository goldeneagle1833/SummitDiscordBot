import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import PostseasonName, { resetBracketMarksCache } from '../BracketMarks'
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

const named = (id) => (
  <PostseasonName playerId={id}>
    <a href={`/player/${id}`}>{id}</a>
  </PostseasonName>
)

describe('PostseasonName', () => {
  beforeEach(() => {
    resetBracketMarksCache()
    getBracketMarks.mockClear()
    getBracketMarks.mockResolvedValue({ success: true, marks: MARKS })
  })

  it.each([
    ['u_champ', 'Champion', 'text-yellow-300'],
    ['u_finalist', 'Finalist', 'text-orange-300'],
    ['u_top4', 'Top 4', 'text-sky-300'],
    ['u_cut', 'Top cut', 'text-violet-300'],
  ])('colours %s by their best finish', async (id, label, colour) => {
    const { container } = renderWithRouter(named(id))
    await waitFor(() => expect(container.querySelector(`[data-finish="${label}"]`)).not.toBeNull())
    expect(container.querySelector('[data-finish]')).toHaveClass(colour)
  })

  it('shows no tag text beside the name', async () => {
    const { container } = renderWithRouter(named('u_finalist'))
    await waitFor(() => expect(container.querySelector('[data-finish]')).not.toBeNull())
    expect(screen.queryByText('Finalist')).not.toBeInTheDocument()
  })

  it('draws one yurt per title', async () => {
    const { container } = renderWithRouter(named('u_double'))
    await waitFor(() => expect(container.querySelectorAll('img')).toHaveLength(2))
  })

  it('gives a finalist no yurt', async () => {
    const { container } = renderWithRouter(named('u_finalist'))
    await waitFor(() => expect(container.querySelector('[data-finish]')).not.toBeNull())
    expect(container.querySelectorAll('img')).toHaveLength(0)
  })

  it('lists every placement on hover', async () => {
    const { container } = renderWithRouter(named('u_double'))
    await waitFor(() => expect(container.querySelector('[data-finish]')).not.toBeNull())

    fireEvent.mouseEnter(container.querySelector('[data-finish]'))
    const card = await screen.findByRole('tooltip')
    expect(card).toHaveTextContent('Cup A')
    expect(card).toHaveTextContent('Cup B')
    expect(card).toHaveTextContent('Champion')

    fireEvent.mouseLeave(container.querySelector('[data-finish]'))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('opens the card for keyboard users too', async () => {
    const { container } = renderWithRouter(named('u_top4'))
    await waitFor(() => expect(container.querySelector('[data-finish]')).not.toBeNull())
    fireEvent.focus(screen.getByRole('link'))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Top 4')
  })

  it('leaves a player with no postseason untouched', async () => {
    const { container } = renderWithRouter(named('u_nobody'))
    await waitFor(() => expect(getBracketMarks).toHaveBeenCalled())
    expect(container.querySelector('[data-finish]')).toBeNull()
    expect(screen.getByRole('link')).toHaveTextContent('u_nobody')
  })

  it('fetches once however many names are on the page', async () => {
    const { container } = renderWithRouter(
      <>
        {named('u_champ')}
        {named('u_finalist')}
        {named('u_nobody')}
      </>,
    )
    await waitFor(() => expect(container.querySelectorAll('[data-finish]')).toHaveLength(2))
    expect(getBracketMarks).toHaveBeenCalledTimes(1)
  })

  it('still shows the name when the marks cannot be loaded', async () => {
    getBracketMarks.mockRejectedValue(new Error('boom'))
    const { container } = renderWithRouter(named('u_champ'))
    await waitFor(() => expect(getBracketMarks).toHaveBeenCalled())
    expect(container.querySelector('[data-finish]')).toBeNull()
    expect(screen.getByRole('link')).toHaveTextContent('u_champ')
  })
})
