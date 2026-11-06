import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/test-utils'
import { HiddenChange, ProvisionalTag, Rating } from '../Provisional'

describe('ProvisionalTag', () => {
  it('shows "Provisional (n/8)"', () => {
    render(<ProvisionalTag games={3} />)
    expect(screen.getByText('Provisional (3/8)')).toBeInTheDocument()
  })
})

describe('Rating', () => {
  it('shows the number for a settled rating', () => {
    render(<Rating obj={{ elo: 1612 }} field="elo" />)
    expect(screen.getByText('1612')).toBeInTheDocument()
    expect(screen.queryByTestId('provisional-tag')).not.toBeInTheDocument()
  })

  it('shows the tag instead of a provisional rating', () => {
    render(<Rating obj={{ elo: null, provisional: true, provisional_games: 6 }} field="elo" />)
    expect(screen.getByText('Provisional (6/8)')).toBeInTheDocument()
  })

  it('reads prefixed flags', () => {
    render(<Rating obj={{ event_elo: null, event_provisional: true, event_provisional_games: 1 }} field="event_elo" prefix="event" />)
    expect(screen.getByText('Provisional (1/8)')).toBeInTheDocument()
  })
})

describe('HiddenChange', () => {
  it('is a muted dash explaining when the change shows', () => {
    render(<HiddenChange />)
    const dash = screen.getByTestId('hidden-change')
    expect(dash).toHaveTextContent('—')
    expect(dash).toHaveAttribute('title', 'Provisional: shown after 8 games')
  })
})
