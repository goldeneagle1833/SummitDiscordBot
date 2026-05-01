import { useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'

export default function Login() {
  usePageTitle('Login')
  useEffect(() => {
  }, [])

  return (
    <div className="max-w-sm mx-auto py-12 space-y-6 text-center">
      <h1 className="text-2xl font-display text-secondary">Login</h1>
      <p className="text-sm text-text-muted">
        Sign in to access your profile and track your stats.
      </p>
      <div className="space-y-3">
        <a
          href="/auth/discord"
          className="block w-full px-5 py-3 bg-[#5865F2] text-white rounded-soft font-medium hover:bg-[#4752C4] transition-colors"
        >
          Login with Discord
        </a>
        <a
          href="/auth/google"
          className="block w-full px-5 py-3 bg-bg-surface border border-border rounded-soft font-medium hover:border-primary/50 transition-colors"
        >
          Login with Google
        </a>
      </div>
    </div>
  )
}
