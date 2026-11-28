import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/test-utils'
import ProfilePictureModal from '../ProfilePictureModal'
import { getProfilePicture, setProfilePicture } from '@/api/players'
import { searchArticleCards } from '@/api/articles'
import { avatarUrl } from '@/utils/avatar'

vi.mock('@/api/players', () => ({
  getProfilePicture: vi.fn(),
  setProfilePicture: vi.fn(() => Promise.resolve({ kind: 'card', card: 'Cherubim', url: '/static/uploads/profile-pictures/x.webp' })),
  uploadProfilePicture: vi.fn(),
  cardPicturePreviewUrl: (id, card) => `/preview/${card}`,
  getRivalOptions: vi.fn(() => Promise.resolve({ players: [] })),
  setShowcase: vi.fn(),
}))
vi.mock('@/api/articles', () => ({
  cardImageUrl: (f) => (f ? `/card-images/${f}` : null),
  searchArticleCards: vi.fn(() => Promise.resolve({ cards: [{ name: 'Cherubim', image: 'got-cherubim-b-s.webp' }] })),
}))

const DISCORD = { kind: 'discord', card: null, url: 'https://cdn/discord.png', discord_url: 'https://cdn/discord.png' }

describe('ProfilePictureModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('starts on the Discord picture, with nothing to save', async () => {
    getProfilePicture.mockResolvedValue(DISCORD)
    renderWithRouter(<ProfilePictureModal playerId="100" onClose={() => {}} />)
    expect(await screen.findByText(/picture from your Discord account/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Discord/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('picks a card and saves its art', async () => {
    getProfilePicture.mockResolvedValue(DISCORD)
    const onSaved = vi.fn()
    const onClose = vi.fn()
    renderWithRouter(<ProfilePictureModal playerId="100" onClose={onClose} onSaved={onSaved} />)
    fireEvent.click(await screen.findByRole('radio', { name: /Card art/ }))
    fireEvent.change(screen.getByLabelText('Card'), { target: { value: 'cher' } })
    await waitFor(() => expect(searchArticleCards).toHaveBeenCalled())
    fireEvent.click(await screen.findByRole('button', { name: 'Cherubim' }))
    expect(screen.getByAltText('Cherubim art')).toHaveAttribute('src', '/preview/Cherubim')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(setProfilePicture).toHaveBeenCalledWith('100', { kind: 'card', card: 'Cherubim' })
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ kind: 'card' }))
  })

  it('goes back to the Discord picture', async () => {
    getProfilePicture.mockResolvedValue({ kind: 'upload', card: null, url: '/static/uploads/profile-pictures/a.webp', discord_url: 'https://cdn/d.png' })
    const onClose = vi.fn()
    renderWithRouter(<ProfilePictureModal playerId="100" onClose={onClose} />)
    fireEvent.click(await screen.findByRole('radio', { name: /Discord/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(setProfilePicture).toHaveBeenCalledWith('100', { kind: 'discord' }))
  })
})

describe('avatarUrl with a picture chosen on the site', () => {
  it('uses it before the Discord picture', () => {
    expect(avatarUrl({ user_id: '1', avatar: 'abc', provider: 'discord', picture_url: '/static/uploads/profile-pictures/p.webp' }))
      .toBe('/static/uploads/profile-pictures/p.webp')
  })
})
