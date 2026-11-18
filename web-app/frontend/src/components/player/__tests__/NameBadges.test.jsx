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
vi.mock('@/components/player/BracketMarks', () => ({ useBracketMarks: () => ({ best_label: 'Champion' }) }))

const EVENT = { folder: 'AotR', event: 'Avatar of the Realm', avatar: 'Druid', label: 'Top Druid', title: 'Top Druid · Avatar of the Realm' }
const paper = (n) => ({ folder: `E${n}`, event: `Event ${n}`, label: 'Top 8', title: `Top 8 · Event ${n}` })

describe('NameBadges', () => {
  beforeEach(() => {
    resetBadgePrefsCache({})
    resetEventAvatarBadgesCache({ 1: [EVENT] })
    resetPaperFinishesCache({ 1: [paper(1), paper(2), paper(3)] })
    resetAvatarHonoursCache({})
  })

  it('shows the best 3 badges as icons, leaving postseason to the name mark', async () => {
    renderWithRouter(<NameBadges playerId="1" />)
    // Champion (postseason) takes a best-3 slot but is shown by the name itself
    await waitFor(() => expect(screen.getAllByRole('link')).toHaveLength(2))
    expect(screen.getByLabelText('Top Druid · Avatar of the Realm')).toHaveAttribute('href', '/player/1?tab=postseason')
    expect(screen.getByLabelText('Top 8 · Event 1')).toBeInTheDocument()
  })

  it("follows the player's own pick", async () => {
    resetBadgePrefsCache({ 1: { shown: ['paper:E3'], hidden: [] } })
    renderWithRouter(<NameBadges playerId="1" />)
    await waitFor(() => expect(screen.getAllByRole('link')).toHaveLength(1))
    expect(screen.getByLabelText('Top 8 · Event 3')).toBeInTheDocument()
  })

  it('renders nothing for a player without badges', () => {
    const { container } = renderWithRouter(<NameBadges playerId="2" />)
    expect(container).toBeEmptyDOMElement()
  })
})
