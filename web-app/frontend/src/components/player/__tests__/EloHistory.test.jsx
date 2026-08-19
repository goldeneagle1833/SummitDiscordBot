import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import EloHistory from '../EloHistory'

const MATCH = {
  date: '2026-08-02T12:00:00',
  elo_after: 1516,
  elo_change: 16,
  result: 'Win',
  opponent: 'Bob',
}

describe('EloHistory', () => {
  it('renders lifetime and every avatar event series together', () => {
    render(
      <EloHistory
        eloHistory={[MATCH]}
        avatarEloHistories={[
          { avatar: 'Impostor', current_elo: 1650, rank: 2, history: [MATCH] },
          { avatar: 'Persecutor', current_elo: 1530, rank: 8, history: [MATCH] },
        ]}
        avatarEvent={{ event_name: 'Avatar League' }}
        showLifetime
        open
        onToggle={vi.fn()}
      />,
    )

    expect(screen.getByText('Lifetime ELO')).toBeInTheDocument()
    expect(screen.getByText('Impostor')).toBeInTheDocument()
    expect(screen.getByText('Persecutor')).toBeInTheDocument()
    expect(screen.getByText('Avatar League · 1650 ELO · Overall #2')).toBeInTheDocument()
    expect(screen.getByText('Avatar League · 1530 ELO · Overall #8')).toBeInTheDocument()
  })
})
