import { Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'

export default function StoreAdminGuard({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner className="py-20" />
  // Storefront admins get in too; the API limits them to their storefronts
  if (!user || !(user.is_store_admin || user.is_store_staff)) return <Navigate to="/" replace />
  return children
}
