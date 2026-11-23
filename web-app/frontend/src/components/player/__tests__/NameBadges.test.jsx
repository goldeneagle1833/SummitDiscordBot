import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import NameBadges, { resetBadgePrefsCache } from '../NameBadges'
import { resetEventAvatarBadgesCache } from '../EventAvatarBadges'
import { resetPaperFinishesCache } from '../PaperFinishes'
import { resetAvatarHonoursCache } from '../AvatarHonours'

vi.mock('@/api/players', () => ({ getProfileBadgePrefs: vi.fn(() => Promise.resolve({ prefs: {} })) }))
vi.mock('@/api/paperFinishes', () => ({ getPaperFinishes: vi.fn(), getEventAvatarBadges: vi.fn() }))
vi.mock('@/api/avatarHonours', () => ({ getAvatarHonours: vi.fn() }))
vi.mock('@/components/player/BracketMarks', async (importOriginal) => ({
  ...(await importOriginal()),
  useBracketMarks: (id) => (String(id) === '1'
    ? { best_label: 'Champion', entries: [{ slug: 's8', label: 'Champion', name: 'Season 8 Top Cut' }] }
    : null),
}))

const EVENT = { folder: 'AotR', event: 'Avatar of the Realm', avatar: 'Druid', label: 'Top Druid', title: 'Top Druid · Avatar of the Realm' }
const paper = (n) => ({ folder: `E${n}`, event: `Event ${n}`, label: 'Top 8', title: `Top 8 · Event ${n}` })

describe('NameBadges', () => {
  beforeEach(() => {
    resetBadgePrefsCache({})
    resetEventAvatarBadgesCache({ 1: [EVENT] })
    resetPaperFinishesCache({ 1: [paper(1), paper(2), paper(3)] })
    resetAvatarHonoursCache({})
  })

  it('shows the best 3 badges as icons, postseason included', async () => {
    renderWithRouter(<NameBadges playerId="1" />)
    await waitFor(() => expect(screen.getAllByRole('link')).toHaveLength(4))
    expect(screen.getByLabelText('2 more on their profile')).toHaveTextContent('+2')
    expect(screen.getByLabelText('Postseason · Champion Champion: Season 8 Top Cut')).toBeInTheDocument()
    expect(screen.getByLabelText('Top Druid · Avatar of the Realm')).toHaveAttribute('href', '/player/1?tab=postseason')
    expect(screen.getByLabelText('Top 8 · Event 1')).toBeInTheDocument()
  })

  it("follows the player's own pick", async () => {
    resetBadgePrefsCache({ 1: { shown: ['paper:E3'], hidden: [] } })
    renderWithRouter(<NameBadges playerId="1" />)
    await waitFor(() => expect(screen.getAllByRole('link')).toHaveLength(2))
    expect(screen.getByLabelText('4 more on their profile')).toBeInTheDocument()
    expect(screen.getByLabelText('Top 8 · Event 3')).toBeInTheDocument()
  })

  it('renders nothing for a player without badges', () => {
    const { container } = renderWithRouter(<NameBadges playerId="2" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('leaves season avatar honours to the profile', async () => {
    const honour = { season: 'Gothic Season 8', avatar: 'Harbinger', place: 1, label: 'Top Harbinger', title: 'Gothic Season 8 Top Harbinger' }
    resetAvatarHonoursCache({ 3: [honour] })
    resetPaperFinishesCache({ 3: [paper(4)] })
    resetBadgePrefsCache({ 3: { shown: ['avatar_honours', 'paper:E4'], hidden: [] } })
    renderWithRouter(<NameBadges playerId="3" />)
    await waitFor(() => expect(screen.getAllByRole('link')).toHaveLength(2))
    expect(screen.getByLabelText('Top 8 · Event 4')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Top Harbinger/)).toBeNull()
    expect(screen.getByLabelText('1 more on their profile')).toHaveTextContent('+1')
  })
})
