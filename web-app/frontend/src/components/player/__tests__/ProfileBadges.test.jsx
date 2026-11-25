import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import { EventAvatarBadgeChips, EventAvatarBadgesSection, resetAvatarFilesCache } from '../EventAvatarBadges'
import ManageBadgesModal from '../ManageBadgesModal'
import { profileBadges, heroBadgeKeys } from '../profileBadges'
import { setShownBadges } from '@/api/players'

vi.mock('@/api/paperFinishes', () => ({ getEventAvatarBadges: vi.fn() }))
vi.mock('@/api/players', () => ({ setShownBadges: vi.fn() }))
vi.mock('@/api/cards', () => ({ getAvatarImageFiles: vi.fn(() => Promise.resolve(['Sparkmage.png'])) }))

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

  it("shows the avatar's portrait in the foil ring, or the foil card without one", () => {
    resetAvatarFilesCache(['Sparkmage.png'])
    const { container } = renderWithRouter(<EventAvatarBadgeChips badges={BADGES} />)
    expect(container.querySelector('.foil-ring img')).toHaveAttribute('src', '/avatar-images/Sparkmage.png')
    resetAvatarFilesCache([])
    const other = renderWithRouter(<EventAvatarBadgeChips badges={BADGES} />)
    expect(other.container.querySelector('.foil-ring')).toBeNull()
    expect(other.container.querySelector('svg')).not.toBeNull()
  })

  it('lists the finish and record in the Postseason tab', () => {
    renderWithRouter(<EventAvatarBadgesSection badges={BADGES} />)
    expect(screen.getByText('Top 16 · 4-2 · best of 7 Sparkmage players')).toBeInTheDocument()
  })
})

describe('Profile badges setting', () => {
  beforeEach(() => vi.mocked(setShownBadges).mockReset())

  const badges = profileBadges({
    marks: { best_label: 'Top 8' },
    honours: [{ place: 1, label: 'Top Imposter', season: 'Gothic Season 8' }],
    paperFinishes: [{ folder: 'LinCon', label: 'Winner', event: 'LinCon' }, { folder: 'Local', label: 'Top 4', event: 'Local' }],
    eventBadges: BADGES,
  })

  it('orders badges best first with stable keys', () => {
    expect(badges.map((b) => b.key)).toEqual([
      'paper:LinCon', 'avatar_honours', 'event_avatar:Avatar of the Realm 2026:Sparkmage', 'paper:Local', 'postseason',
    ])
  })

  it("drops a paper result that repeats the player's Summit postseason finish", () => {
    const marks = { best_label: 'Top 4', entries: [{ label: 'Top 4', name: 'Gothic Season 4 Top Cut' }] }
    const keys = profileBadges({
      marks,
      paperFinishes: [
        { folder: 'S4', label: 'Top 4', event: 'Summit Gothic Season 4' },
        { folder: 'S5', label: 'Top 8', event: 'Summit Gothic Season 5' },
        { folder: 'Ascanrask', label: 'Winner', event: 'Ascanrask III' },
      ],
    }).map((b) => b.key)
    expect(keys).toEqual(['paper:Ascanrask', 'postseason', 'paper:S5'])
  })

  it('shows the best 3 by default, or exactly what the player picked', () => {
    expect([...heroBadgeKeys(badges, null)]).toEqual(['paper:LinCon', 'avatar_honours', 'event_avatar:Avatar of the Realm 2026:Sparkmage'])
    expect([...heroBadgeKeys(badges, ['postseason', 'gone'])]).toEqual(['postseason'])
    expect(heroBadgeKeys(badges, []).size).toBe(0)
    expect([...heroBadgeKeys(badges, null, ['paper:LinCon'])]).toEqual([
      'avatar_honours', 'event_avatar:Avatar of the Realm 2026:Sparkmage', 'paper:Local',
    ])
  })

  it('saves the picked badges, best first', async () => {
    vi.mocked(setShownBadges).mockResolvedValue({ shown: ['paper:LinCon', 'avatar_honours', 'event_avatar:Avatar of the Realm 2026:Sparkmage', 'postseason'] })
    const onSaved = vi.fn()
    renderWithRouter(<ManageBadgesModal playerId="1" badges={badges} shown={null} onClose={() => {}} onSaved={onSaved} />)
    expect(screen.getByText('3 of 5 showing (your best 3)')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Best postseason finish'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(setShownBadges).toHaveBeenCalledWith('1', [
      'paper:LinCon', 'avatar_honours', 'event_avatar:Avatar of the Realm 2026:Sparkmage', 'postseason',
    ])
  })

  it('goes back to the best 3', async () => {
    vi.mocked(setShownBadges).mockResolvedValue({ shown: null })
    const onSaved = vi.fn()
    renderWithRouter(<ManageBadgesModal playerId="1" badges={badges} shown={['postseason']} onClose={() => {}} onSaved={onSaved} />)
    fireEvent.click(screen.getByRole('button', { name: 'Use my best 3' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(null))
    expect(setShownBadges).toHaveBeenCalledWith('1', null)
  })
})
