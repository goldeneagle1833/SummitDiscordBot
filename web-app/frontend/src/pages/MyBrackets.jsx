import { Link } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import BracketsAdmin from './admin/BracketsAdmin'

/**
 * `/brackets/manage`: where a player with the Bracket Organizer role on the
 * Summit Discord creates and runs their own (community) brackets.
 */
export default function MyBrackets() {
  usePageTitle('My Brackets')
  const { user, loading } = useAuth()

  if (loading) return <Spinner />
  if (!user) {
    return (
      <div className="max-w-xl mx-auto px-4 py-12 text-center space-y-2">
        <h1 className="text-2xl font-display">My Brackets</h1>
        <p className="text-text-muted">
          <Link to="/login" className="text-secondary hover:underline">Log in with Discord</Link>{' '}
          to run a bracket.
        </p>
      </div>
    )
  }
  if (!user.is_bracket_organizer) {
    return (
      <div className="max-w-xl mx-auto px-4 py-12 text-center space-y-2">
        <h1 className="text-2xl font-display">My Brackets</h1>
        <p className="text-text-muted">
          Running a bracket needs the Bracket Organizer role on the Summit Discord. Ask an admin
          if you’d like to host one.
        </p>
        <Link to="/brackets" className="text-secondary hover:underline text-sm">
          Back to brackets
        </Link>
      </div>
    )
  }
  return <BracketsAdmin organizer />
}
