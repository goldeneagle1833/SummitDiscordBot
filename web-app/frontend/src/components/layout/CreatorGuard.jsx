import { Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'

export default function CreatorGuard({ children }) {
  const { user, loading } = useAuth()

  if (loading) return <Spinner className="py-20" />
  if (!user || (!user.is_creator && !user.is_admin)) return <Navigate to="/" replace />

  return children
}
