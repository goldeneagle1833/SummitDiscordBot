import { createContext, useContext, useState, useEffect } from 'react'
import { getMe } from '@/api/auth'

const AuthContext = createContext(null)

// Waits between retries when /api/me fails for a reason other than "not
// logged in" (a network blip, a server restart during a deploy, a slow
// worker). Without retries any hiccup on page load showed a signed-in player
// as logged out until they reloaded.
export const ME_RETRY_DELAYS_MS = [700, 2000]

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** Fetch the current user. A 401 means logged out; anything else is retried. */
export async function loadMe(delays = ME_RETRY_DELAYS_MS) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await getMe()
    } catch (err) {
      if (err?.status === 401 || attempt >= delays.length) throw err
      await wait(delays[attempt])
    }
  }
}

export function AuthProvider({ children }) {
  // null = loading, false = unauthenticated, object = authenticated
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadMe()
      .then((data) => setUser(data))
      .catch(() => setUser(false))
      .finally(() => setLoading(false))
  }, [])

  const refreshUser = () => {
    return loadMe()
      .then((data) => setUser(data))
      .catch(() => setUser(false))
  }

  return (
    <AuthContext.Provider value={{ user, loading, setUser, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
