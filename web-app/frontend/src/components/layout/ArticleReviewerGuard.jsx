import { Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'

// Admins and the article reviewers (ARTICLE_REVIEWER_IDS on the server).
export default function ArticleReviewerGuard({ children }) {
  const { user, loading } = useAuth()

  if (loading) return <Spinner className="py-20" />
  if (!user || !(user.is_admin || user.is_article_reviewer)) return <Navigate to="/" replace />

  return children
}
