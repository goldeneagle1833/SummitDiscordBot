import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'

/**
 * Gates pages that need any logged-in user (no role required).
 * Signed-out visitors are sent to the login page and brought back afterwards.
 */
export default function LoginGuard({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Spinner className="py-20" />
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return children
}
