import { describe, it, expect, vi, afterEach } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import MatchHistoryTable from '../MatchHistoryTable'

const match = (id, voice) => ({
  match_id: id,
  result: 'Win',
  match_type: 'ranked',
  opponent: `Opp ${id}`,
  opponent_id: `${id}`,
  elo_change: 12,
  date: '2026-09-21T12:00:00',
  voice,
})

describe('MatchHistoryTable voice column', () => {
  it('shows the voice icon to visitors, not just the owner', () => {
    renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[match(1, true)]} isOwner={false} />
    )
    expect(screen.getByRole('img', { name: 'Voice' })).toBeInTheDocument()
  })

  it('shows the voice emojis for voice, no-voice and untracked matches', () => {
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[match(1, true), match(2, false), match(3, undefined)]}
        isOwner={false}
      />
    )
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByRole('img', { name: 'Voice' })).toHaveTextContent('🔊')
    expect(within(rows[1]).getByRole('img', { name: 'No voice' })).toHaveTextContent('🔇')
    expect(within(rows[2]).queryByRole('img')).not.toBeInTheDocument()
  })
})

describe('MatchHistoryTable replay column', () => {
  it('links to the replay when the match has one', () => {
    const replay = 'https://playsorceryonline.com/replay/abc123'
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[{ ...match(1, true), replay_url: replay }, match(2, true)]}
        isOwner={false}
      />
    )
    expect(screen.getByRole('columnheader', { name: 'Replay' })).toBeInTheDocument()
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByRole('link', { name: 'Watch' })).toHaveAttribute('href', replay)
    expect(within(rows[1]).queryByRole('link', { name: 'Watch' })).not.toBeInTheDocument()
  })
})

describe('MatchHistoryTable column order', () => {
  const headers = () => screen.getAllByRole('columnheader').map((th) => th.textContent)

  it('puts Replay between Rating and Play/Draw for visitors', () => {
    renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[match(1, true)]} isOwner={false} />
    )
    expect(headers()).toEqual(['Result', 'Type', 'Opponent', 'Rating', 'Replay', 'Play/Draw', 'Date'])
  })

  it('puts Notes then Change Result last for the owner', () => {
    renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[match(1, true)]} isOwner />
    )
    const h = headers()
    expect(h.indexOf('Replay')).toBe(h.indexOf('Rating') + 1)
    expect(h.indexOf('Play/Draw')).toBe(h.indexOf('Replay') + 1)
    expect(h.slice(-2)).toEqual(['Notes', 'Change Result'])
  })

  it('fits the owner view in 11 columns with no forced minimum width', () => {
    renderWithRouter(
      <MatchHistoryTable
        title="Match History"
        matches={[{ ...match(1, true), player_avatar: 'Druid', opponent_avatar: 'Seer', deck_elements: ['Fire'], opponent_elements: ['Water'], match_time: 12 }]}
        isOwner
        onEditDeck={() => {}}
      />
    )
    expect(headers()).toEqual(['Result', 'Type', 'Avatar', 'Opponent', 'Rating', 'Replay', 'Play/Draw', 'Date', 'Deck', 'Notes', 'Change Result'])
    expect(screen.getByRole('table').style.minWidth).toBe('')
    const row = screen.getAllByRole('row')[1]
    expect(within(row).getByRole('link', { name: 'Druid' })).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Seer' })).toBeInTheDocument()
    expect(within(row).getByAltText('Fire')).toBeInTheDocument()
    expect(within(row).getByAltText('Water')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: '12 min' })).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Edit deck link' })).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: '+ Note' })).toBeInTheDocument()
    expect(row).toHaveTextContent('#1')
  })
})

describe('MatchHistoryTable on a phone', () => {
  afterEach(() => { delete window.matchMedia })

  it('shows one card per match instead of a wide table, with every action', () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: query.includes('max-width: 1023px'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    renderWithRouter(
      <MatchHistoryTable
        title="Match History"
        matches={[{ ...match(3, false), match_source: 'bot', player_avatar: 'Druid', opponent_avatar: 'Seer', replay_url: 'https://x/replay/1', first_player: 'Play', has_deck_json: true }]}
        isOwner
        playerId="9"
        onEditDeck={() => {}}
      />
    )
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    const card = screen.getByTestId('match-cards')
    expect(within(card).getByText('Win')).toBeInTheDocument()
    expect(within(card).getByRole('img', { name: 'No voice' })).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Opp 3' })).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Watch' })).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Snapshot' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Edit deck link' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: '+ Note' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Change Result' })).toBeInTheDocument()
    expect(card).toHaveTextContent('Play')
    expect(card).toHaveTextContent('+12')
  })
})

describe('MatchHistoryTable provisional Rating changes', () => {
  it('shows a muted dash with a tooltip for a hidden change', () => {
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[{ ...match(1, true), elo_change: null, elo_change_hidden: true }]}
        isOwner={false}
      />
    )
    const row = screen.getAllByRole('row')[1]
    const dash = within(row).getByTestId('hidden-change')
    expect(dash).toHaveTextContent('\u2014')
    expect(dash).toHaveAttribute('title', 'Provisional: shown after 8 games')
    expect(row).not.toHaveTextContent('+0')
    expect(row).not.toHaveTextContent('null')
    expect(row).not.toHaveTextContent('NaN')
  })

  it('still shows a settled change as before', () => {
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[match(1, true), { ...match(2, true), result: 'Loss', elo_change: -9 }]}
        isOwner={false}
      />
    )
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('+12')).toBeInTheDocument()
    expect(within(rows[1]).getByText('-9')).toBeInTheDocument()
    expect(screen.queryByTestId('hidden-change')).toBeNull()
  })
})


describe('MatchHistoryTable type column', () => {
  it('labels casual (and testing, the bot casual type) as Casual, plus Omens and ranked', () => {
    renderWithRouter(
      <MatchHistoryTable
        title="Match History"
        matches={[
          { ...match(1, true), match_type: 'casual' },
          { ...match(2, true), match_type: 'testing' },
          { ...match(3, true), match_type: 'points' },
          match(4, true),
        ]}
        isOwner={false}
      />
    )
    const rows = screen.getAllByRole('row').slice(1)
    const typeCell = (row) => within(row).getAllByRole('cell')[1]
    expect(typeCell(rows[0])).toHaveTextContent('Casual')
    expect(typeCell(rows[1])).toHaveTextContent('Casual')
    expect(typeCell(rows[2])).toHaveTextContent('Omens')
    expect(typeCell(rows[3])).toHaveTextContent('Ranked')
  })
})

describe('MatchHistoryTable Change Result button', () => {
  it('is only shown to the owner, for this season\'s bot matches', () => {
    const { unmount } = renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[{ ...match(1, true), match_source: 'bot' }]} isOwner={false} />
    )
    expect(screen.queryByRole('columnheader', { name: 'Change Result' })).not.toBeInTheDocument()
    unmount()
    renderWithRouter(
      <MatchHistoryTable
        title="Ranked Match History"
        matches={[
          { ...match(1, true), match_source: 'bot' },
          { ...match(2, true), match_source: 'web' },
          { ...match(1000000005, true), match_source: 'bot' },
        ]}
        isOwner
      />
    )
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByRole('button', { name: 'Change Result' })).toBeInTheDocument()
    expect(within(rows[1]).queryByRole('button', { name: 'Change Result' })).not.toBeInTheDocument()
    expect(within(rows[2]).queryByRole('button', { name: 'Change Result' })).not.toBeInTheDocument()
  })

  it('asks before sending and explains the opponent must confirm', async () => {
    const { fireEvent } = await import('@testing-library/react')
    renderWithRouter(
      <MatchHistoryTable title="Ranked Match History" matches={[{ ...match(7, true), match_source: 'bot' }]} isOwner />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Change Result' }))
    const dialog = screen.getByRole('dialog', { name: 'Change result' })
    expect(dialog).toHaveTextContent('Switch it to a loss?')
    expect(dialog).toHaveTextContent('Opp 7 gets a Discord DM to confirm')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
