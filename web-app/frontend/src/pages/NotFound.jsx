import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

export default function NotFound() {
  usePageTitle('404 Not Found')

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center">
      <h1 className="text-6xl font-display text-primary mb-4">404</h1>
      <p className="text-xl text-text-muted mb-6">Page not found</p>
      <Link
        to="/"
        className="bg-primary/20 text-primary hover:bg-primary/30 px-4 py-2 rounded-soft transition-colors"
      >
        Back to Home
      </Link>
    </div>
  )
}
