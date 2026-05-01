import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getAvatar } from '@/api/cards'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function AvatarDetail() {
  usePageTitle('Avatar Detail')
  const { name } = useParams()
  const [avatar, setAvatar] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getAvatar(name)
      .then((data) => {
        setAvatar(data)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [name])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!avatar) return null

  return (
    <div className="space-y-6">
      <Link to="/avatars" className="text-primary hover:text-primary-light text-sm">&larr; All Avatars</Link>

      <div className="bg-bg-surface border border-border rounded-soft p-6 flex flex-col sm:flex-row gap-6">
        {avatar.image_url && (
          <img
            src={avatar.image_url}
            alt={avatar.name}
            className="w-40 h-40 object-cover rounded flex-shrink-0"
          />
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-display text-secondary mb-2">{avatar.name}</h1>
          {avatar.element && (
            <p className="text-sm text-text-muted mb-3">Element: <span className="text-text">{avatar.element}</span></p>
          )}
          <div className="flex gap-4 text-sm">
            <span className="text-accent-green">{avatar.wins ?? 0} Wins</span>
            <span className="text-accent-red">{avatar.losses ?? 0} Losses</span>
            {avatar.win_rate != null && (
              <span className="text-text-muted">{(avatar.win_rate * 100).toFixed(1)}% Win Rate</span>
            )}
          </div>
        </div>
      </div>

      {avatar.top_players?.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Top Players</h2>
          <div className="space-y-2">
            {avatar.top_players.map((player) => (
              <Link
                key={player.player_id}
                to={`/player/${player.player_id}`}
                className="bg-bg-surface border border-border rounded-soft p-3 flex items-center justify-between hover:border-primary/50 transition-colors"
              >
                <span className="text-sm font-medium">{player.display_name}</span>
                <span className="text-xs text-text-muted">
                  <span className="text-accent-green">{player.wins}W</span>
                  {' / '}
                  <span className="text-accent-red">{player.losses}L</span>
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
