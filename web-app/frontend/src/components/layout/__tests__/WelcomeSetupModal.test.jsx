import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, render, waitFor, fireEvent } from '@testing-library/react'
import { AuthProvider } from '@/context/AuthContext'
import WelcomeSetupModal from '../WelcomeSetupModal'

vi.mock('@/api/auth', () => ({ getMe: vi.fn(), finishWelcome: vi.fn() }))
vi.mock('@/api/players', () => ({ setDisplayName: vi.fn(), setShowcase: vi.fn(), getRivalOptions: vi.fn() }))
vi.mock('@/api/articles', () => ({
  searchArticleCards: vi.fn(() => Promise.resolve({ cards: [{ name: 'Spire', image: 'spire' }] })),
  cardImageUrl: (x) => `/img/${x}`,
}))

import { getMe, finishWelcome } from '@/api/auth'
import { setDisplayName, setShowcase } from '@/api/players'

const NEW_PLAYER = { user_id: '1000000000000001', username: 'Player 0001', auth_provider: 'email', needs_welcome: true }

function renderModal(user) {
  getMe.mockResolvedValue(user)
  return render(<AuthProvider><WelcomeSetupModal /></AuthProvider>)
}

describe('WelcomeSetupModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    finishWelcome.mockResolvedValue({ success: true })
    setDisplayName.mockResolvedValue({ success: true })
    setShowcase.mockResolvedValue({ success: true })
  })

  it('stays hidden for players who are already set up', async () => {
    renderModal({ ...NEW_PLAYER, needs_welcome: false })
    await waitFor(() => expect(getMe).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('saves the username and favorite card', async () => {
    renderModal(NEW_PLAYER)
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'Gee Wiz' } })
    fireEvent.change(screen.getByLabelText(/Favorite card/), { target: { value: 'Spi' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Spire' }))
    getMe.mockResolvedValue({ ...NEW_PLAYER, username: 'Gee Wiz', needs_welcome: false })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(setDisplayName).toHaveBeenCalledWith('1000000000000001', 'Gee Wiz')
    expect(setShowcase).toHaveBeenCalledWith('1000000000000001', { favorite_card: 'Spire' })
    expect(finishWelcome).toHaveBeenCalled()
  })

  it('asks for a username before saving', async () => {
    renderModal(NEW_PLAYER)
    fireEvent.click(await screen.findByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/Pick a username/)).toBeInTheDocument()
    expect(setDisplayName).not.toHaveBeenCalled()
  })

  it('"Not now" closes it for good without renaming', async () => {
    renderModal(NEW_PLAYER)
    fireEvent.click(await screen.findByRole('button', { name: 'Not now' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(finishWelcome).toHaveBeenCalled()
    expect(setDisplayName).not.toHaveBeenCalled()
  })
})
