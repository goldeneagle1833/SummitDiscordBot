import { useEffect } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

// Profile panels that a link can open straight away, e.g. /me/block-list.
// Partner sites (Play Sorcery Online) link here because they don't need to
// know the player's Summit id: the logged-in player lands on their own page.
export const OPENABLE_PANELS = ['block-list']

export default function MyProfile() {
  const { panel } = useParams()
  const { user, loading } = useAuth()
  const known = OPENABLE_PANELS.includes(panel)

  useEffect(() => {
    if (!loading && !user) {
      // Log in first, then come straight back to this link
      const next = window.location.origin + window.location.pathname
      window.location.replace(`/login?next=${encodeURIComponent(next)}`)
    }
  }, [loading, user])

  if (loading || !user) {
    return <p className="text-text-muted py-12 text-center">Opening your profile…</p>
  }
  const qs = known ? `?open=${panel}` : ''
  return <Navigate to={`/player/${encodeURIComponent(user.user_id)}${qs}`} replace />
}
