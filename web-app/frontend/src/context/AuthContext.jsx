import { createContext, useContext, useState, useEffect } from 'react'
import { getMe } from '@/api/auth'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // null = loading, false = unauthenticated, object = authenticated
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMe()
      .then((data) => setUser(data))
      .catch(() => setUser(false))
      .finally(() => setLoading(false))
  }, [])

  const refreshUser = () => {
    return getMe()
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
