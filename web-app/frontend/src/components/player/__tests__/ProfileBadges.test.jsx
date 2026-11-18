import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { EventAvatarBadgeChips, EventAvatarBadgesSection } from '../EventAvatarBadges'
import ManageBadgesModal from '../ManageBadgesModal'
import { profileBadges } from '../profileBadges'
import { setHiddenBadges } from '@/api/players'

vi.mock('@/api/paperFinishes', () => ({ getEventAvatarBadges: vi.fn() }))
vi.mock('@/api/players', () => ({ setHiddenBadges: vi.fn() }))

const BADGES = [
  {
    folder: 'Avatar of the Realm 2026', event: 'Avatar Of The Realm', avatar: 'Sparkmage',
    label: 'Top Sparkmage', title: 'Top Sparkmage · Avatar Of The Realm', place: 9, finish: 'Top 16',
    wins: 4, losses: 2, draws: 0, avatar_players: 7,
  },
]

describe('Event avatar badges', () => {
  it('shows a chip linking to the event', () => {
    renderWithRouter(<EventAvatarBadgeChips badges={BADGES} />)
    expect(screen.getByText('Top Sparkmage')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', '/top-8/Avatar%20of%20the%20Realm%202026')
  })

  it('lists the finish and record in the Postseason tab', () => {
    renderWithRouter(<EventAvatarBadgesSection badges={BADGES} />)
    expect(screen.getByText('Top 16 · 4-2 · best of 7 Sparkmage players')).toBeInTheDocument()
  })
})

describe('Profile badges setting', () => {
  beforeEach(() => vi.mocked(setHiddenBadges).mockReset())

  const badges = profileBadges({
    marks: { best_label: 'Champion' },
    honours: [{ place: 1, label: 'Top Imposter', season: 'Gothic Season 8' }],
    paperFinishes: [{ folder: 'LinCon', label: 'Top 8', event: 'LinCon' }],
    eventBadges: BADGES,
  })

  it('builds one entry per hero badge with stable keys', () => {
    expect(badges.map((b) => b.key)).toEqual([
      'postseason', 'avatar_honours', 'event_avatar:Avatar of the Realm 2026:Sparkmage', 'paper:LinCon',
    ])
  })

  it('saves the badges the player switched off', async () => {
    vi.mocked(setHiddenBadges).mockResolvedValue({ hidden: ['paper:LinCon'] })
    const onSaved = vi.fn()
    renderWithRouter(
      <ManageBadgesModal playerId="1" badges={badges} hidden={['stale-key']} onClose={() => {}} onSaved={onSaved} />,
    )
    expect(screen.getByText('4 of 4 showing')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('checkbox')[3])
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(['paper:LinCon']))
    expect(setHiddenBadges).toHaveBeenCalledWith('1', ['paper:LinCon'])
  })
})
