import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MatchFilters from '../MatchFilters'

const data = {
  options: {
    opponents: [{ id: '200', name: 'Geoffrey', games: 4 }, { id: '300', name: 'Bob', games: 1 }],
    avatars: ['Pathfinder'],
    opponent_avatars: ['Seer'],
  },
  active: {},
  ranked: { wins: 1, losses: 2 },
  casual: { wins: 0, losses: 0 },
}

describe('MatchFilters', () => {
  it('picks an opponent and remembers their name', async () => {
    const onChange = vi.fn()
    render(<MatchFilters filters={{}} data={data} onChange={onChange} />)
    await userEvent.selectOptions(screen.getByLabelText('Opponent'), '200')
    expect(onChange).toHaveBeenCalledWith({ opponent: '200', opponentName: 'Geoffrey' })
  })

  it('shows the record for the filtered games and clears', async () => {
    const onChange = vi.fn()
    render(<MatchFilters filters={{ opponent: '200', opponentName: 'Geoffrey' }} data={data} onChange={onChange} />)
    expect(screen.getByTestId('filter-record')).toHaveTextContent('Ranked: 1W - 2L (33.3%)')
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(onChange).toHaveBeenCalledWith({})
  })

  it('keeps a picked opponent who has no games in this period', () => {
    const empty = { ...data, options: { opponents: [], avatars: [], opponent_avatars: [] } }
    render(<MatchFilters filters={{ opponent: '200', opponentName: 'Geoffrey' }} data={empty} onChange={() => {}} />)
    expect(screen.getByLabelText('Opponent')).toHaveDisplayValue('Geoffrey')
  })

  it('filters to games on the draw', async () => {
    const onChange = vi.fn()
    render(<MatchFilters filters={{}} data={data} onChange={onChange} />)
    await userEvent.selectOptions(screen.getByLabelText('Play/Draw'), 'draw')
    expect(onChange).toHaveBeenCalledWith({ play_draw: 'draw' })
  })

  it('hides the card filter when the viewer may not see card data', () => {
    render(<MatchFilters filters={{}} data={data} onChange={() => {}} />)
    expect(screen.queryByLabelText('Card played')).toBeNull()
  })

  it('filters to games where a card was played', async () => {
    const onChange = vi.fn()
    const withCards = { ...data, options: { ...data.options, cards: [{ name: 'Desert', games: 3 }], card_games: 5 } }
    render(<MatchFilters filters={{}} data={withCards} onChange={onChange} />)
    await userEvent.type(screen.getByLabelText('Card played'), 'desert')
    expect(onChange).toHaveBeenCalledWith({ card: 'Desert' })
  })

  it('clears the card filter when the box is emptied', async () => {
    const onChange = vi.fn()
    const withCards = { ...data, options: { ...data.options, cards: [{ name: 'Desert', games: 3 }], card_games: 5 } }
    render(<MatchFilters filters={{ card: 'Desert' }} data={withCards} onChange={onChange} />)
    expect(screen.getByText(/only counts games with card data/)).toHaveTextContent('5 games in this period')
    await userEvent.clear(screen.getByLabelText('Card played'))
    expect(onChange).toHaveBeenCalledWith({})
  })
})
