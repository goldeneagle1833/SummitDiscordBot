import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithRouter } from '@/test/test-utils'
import BracketTree from '../BracketTree'

function match(overrides = {}) {
  return {
    match_no: 1,
    round: 1,
    round_title: 'Round 1',
    position: 1,
    state: 'pending',
    playable: true,
    p1_seed: 1,
    p1_name: 'One',
    p1_user_id: 'u1',
    p2_seed: 8,
    p2_name: 'Eight',
    p2_user_id: 'u8',
    ...overrides,
  }
}

const rounds = (matches) => [{ round: 1, title: 'Round 1', matches }]

describe('BracketTree', () => {
  it('renders both players with their seeds', () => {
    renderWithRouter(<BracketTree rounds={rounds([match()])} />)
    expect(screen.getByText('One')).toBeInTheDocument()
    expect(screen.getByText('Eight')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
  })

  it('links players to their profile', () => {
    renderWithRouter(<BracketTree rounds={rounds([match()])} />)
    expect(screen.getByText('One').closest('a')).toHaveAttribute('href', '/player/u1')
  })

  it('shows a waiting slot when the opponent is undecided', () => {
    renderWithRouter(
      <BracketTree rounds={rounds([match({ p2_seed: null, p2_name: null, playable: false })])} />,
    )
    expect(screen.getByText('Waiting')).toBeInTheDocument()
  })

  it('strikes through the loser of a finished match', () => {
    renderWithRouter(
      <BracketTree
        rounds={rounds([match({ state: 'complete', winner_seed: 1, winner_user_id: 'u1' })])}
      />,
    )
    // The loser's name is struck through; the winner's row is highlighted.
    expect(screen.getByText('Eight').className).toContain('line-through')
    expect(screen.getByText('One').closest('div').className).toContain('font-semibold')
  })

  it('offers a report button only to a player in the match', async () => {
    const onReport = vi.fn()
    renderWithRouter(
      <BracketTree rounds={rounds([match({ viewer_can_report: true })])} onReport={onReport} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /report result/i }))
    expect(onReport).toHaveBeenCalledWith(expect.objectContaining({ match_no: 1 }))
  })

  it('hides the report button from everyone else', () => {
    renderWithRouter(<BracketTree rounds={rounds([match()])} />)
    expect(screen.queryByRole('button', { name: /report result/i })).not.toBeInTheDocument()
  })

  it('offers confirm and dispute to the opponent of a reported match', async () => {
    const onConfirm = vi.fn()
    renderWithRouter(
      <BracketTree
        rounds={rounds([
          match({ state: 'reported', reported_winner_id: 'u1', viewer_can_confirm: true }),
        ])}
        onConfirm={onConfirm}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ match_no: 1 }), true)

    await userEvent.click(screen.getByRole('button', { name: 'Dispute' }))
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ match_no: 1 }), false)
  })

  it('tells bystanders a result is awaiting confirmation', () => {
    renderWithRouter(
      <BracketTree rounds={rounds([match({ state: 'reported', reported_winner_id: 'u1' })])} />,
    )
    expect(screen.getByText('Awaiting confirmation')).toBeInTheDocument()
    expect(screen.getByText('reported')).toBeInTheDocument()
  })

  it('gives admins win and reset controls', async () => {
    const onAdminAction = vi.fn()
    const { rerender } = renderWithRouter(
      <BracketTree rounds={rounds([match()])} isAdmin onAdminAction={onAdminAction} />,
    )
    await userEvent.click(screen.getByTitle('Give the win to Eight'))
    expect(onAdminAction).toHaveBeenCalledWith('result', expect.any(Object), 'u8')

    rerender(
      <BracketTree
        rounds={rounds([match({ state: 'complete', winner_seed: 1, winner_user_id: 'u1' })])}
        isAdmin
        onAdminAction={onAdminAction}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(onAdminAction).toHaveBeenCalledWith('reset', expect.any(Object))
  })

  it('tags a player who advanced on a bye', () => {
    renderWithRouter(
      <BracketTree
        rounds={rounds([match({ p1_from_bye: true, p2_name: null, p2_seed: null })])}
      />,
    )
    expect(screen.getByText('bye')).toBeInTheDocument()
    expect(screen.getByText('bye')).toHaveAttribute(
      'title',
      'Advanced on a first-round bye',
    )
  })

  it('swaps two players when one name is dropped on another', () => {
    const onSwap = vi.fn()
    renderWithRouter(<BracketTree rounds={rounds([match()])} onSwap={onSwap} />)

    const store = {}
    const dataTransfer = {
      setData: (_, value) => {
        store.value = value
      },
      getData: () => store.value,
    }

    fireEvent.dragStart(screen.getByText('One'), { dataTransfer })
    fireEvent.drop(screen.getByText('Eight'), { dataTransfer })

    expect(onSwap).toHaveBeenCalledWith(1, 8)
  })

  it('ignores a name dropped on itself', () => {
    const onSwap = vi.fn()
    renderWithRouter(<BracketTree rounds={rounds([match()])} onSwap={onSwap} />)

    const store = {}
    const dataTransfer = {
      setData: (_, value) => {
        store.value = value
      },
      getData: () => store.value,
    }

    fireEvent.dragStart(screen.getByText('One'), { dataTransfer })
    fireEvent.drop(screen.getByText('One'), { dataTransfer })

    expect(onSwap).not.toHaveBeenCalled()
  })

  it('does not make names draggable without a swap handler', () => {
    renderWithRouter(<BracketTree rounds={rounds([match()])} />)
    // Names stay profile links when the tree is not being arranged.
    expect(screen.getByText('One').closest('a')).toHaveAttribute('href', '/player/u1')
  })

  it('shows each player profile picture', () => {
    const { container } = renderWithRouter(
      <BracketTree
        rounds={rounds([match()])}
        avatars={{ u1: 'https://cdn.example/u1.png' }}
      />,
    )
    const images = [...container.querySelectorAll('img')]
    expect(images).toHaveLength(1)
    expect(images[0]).toHaveAttribute('src', 'https://cdn.example/u1.png')
  })

  it('counts how far a round has got', () => {
    renderWithRouter(
      <BracketTree
        rounds={[
          {
            round: 1,
            title: 'Semifinals',
            matches: [
              match({ state: 'complete', winner_seed: 1 }),
              match({ match_no: 2 }),
            ],
          },
        ]}
      />,
    )
    expect(screen.getByText('1/2 done')).toBeInTheDocument()
  })

  it('lays rounds out left to right', () => {
    renderWithRouter(
      <BracketTree
        rounds={[
          { round: 1, title: 'Semifinals', matches: [match()] },
          { round: 2, title: 'Finals', matches: [match({ match_no: 2 })] },
        ]}
      />,
    )
    const headings = screen.getAllByRole('heading')
    expect(headings.map((h) => h.textContent)).toEqual(['Semifinals', 'Finals'])
  })

  it('handles a bracket with no matches', () => {
    renderWithRouter(<BracketTree rounds={[]} />)
    expect(screen.getByText(/no matches yet/i)).toBeInTheDocument()
  })
})
