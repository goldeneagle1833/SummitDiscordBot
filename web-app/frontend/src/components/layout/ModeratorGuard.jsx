import { Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'

// Mod Tools: moderators and admins. The API checks too.
export default function ModeratorGuard({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner className="py-20" />
  if (!user || !(user.is_moderator || user.is_admin)) return <Navigate to="/" replace />
  return children
}
