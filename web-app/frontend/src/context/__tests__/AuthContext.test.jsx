import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth, loadMe } from '../AuthContext'

vi.mock('@/api/auth', () => ({
  getMe: vi.fn(),
}))

import { getMe } from '@/api/auth'

function wrapper({ children }) {
  return <AuthProvider>{children}</AuthProvider>
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts in loading state', () => {
    getMe.mockReturnValue(new Promise(() => {})) // never resolves
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.loading).toBe(true)
    expect(result.current.user).toBeNull()
  })

  it('sets user on successful auth', async () => {
    const mockUser = { user_id: '123', username: 'TestUser', is_admin: false }
    getMe.mockResolvedValue(mockUser)
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toEqual(mockUser)
  })

  it('sets user to false on auth failure', async () => {
    getMe.mockRejectedValue(Object.assign(new Error('Unauthorized'), { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBe(false)
  })

  it('does not retry a 401 (really logged out)', async () => {
    getMe.mockRejectedValue(Object.assign(new Error('Unauthorized'), { status: 401 }))
    await expect(loadMe([0, 0])).rejects.toThrow('Unauthorized')
    expect(getMe).toHaveBeenCalledTimes(1)
  })

  it('retries a network or server error and keeps the player signed in', async () => {
    const mockUser = { user_id: '123', username: 'TestUser' }
    getMe
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(Object.assign(new Error('Bad Gateway'), { status: 502 }))
      .mockResolvedValue(mockUser)
    await expect(loadMe([0, 0])).resolves.toEqual(mockUser)
    expect(getMe).toHaveBeenCalledTimes(3)
  })

  it('gives up after the last retry', async () => {
    getMe.mockRejectedValue(Object.assign(new Error('Server error'), { status: 500 }))
    await expect(loadMe([0, 0])).rejects.toThrow('Server error')
    expect(getMe).toHaveBeenCalledTimes(3)
  })

  it('throws when used outside AuthProvider', () => {
    expect(() => {
      renderHook(() => useAuth())
    }).toThrow('useAuth must be used within an AuthProvider')
  })
})
