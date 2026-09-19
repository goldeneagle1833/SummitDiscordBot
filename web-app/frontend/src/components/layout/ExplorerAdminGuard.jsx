import { Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'

/**
 * Gates Explorer Series admin pages. Global admins are a superset of Explorer
 * admins, matching is_explorer_admin() on the server.
 */
export default function ExplorerAdminGuard({ children }) {
  const { user, loading } = useAuth()

  if (loading) return <Spinner className="py-20" />
  if (!user || !(user.is_explorer_admin || user.is_admin)) return <Navigate to="/" replace />

  return children
}
