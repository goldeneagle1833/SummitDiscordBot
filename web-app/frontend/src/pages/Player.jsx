import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { getPlayer, getPlayerAvatarStats } from '@/api/players'
import PlayerCard from '@/components/player/PlayerCard'
import Spinner from '@/components/ui/Spinner'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

export default function Player() {
  usePageTitle('Player')
  const { playerId } = useParams()
  const [profile, setProfile] = useState(null)
  const [avatarStats, setAvatarStats] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([getPlayer(playerId), getPlayerAvatarStats(playerId).catch(() => [])])
      .then(([profileData, statsData]) => {
        setProfile(profileData)
        setAvatarStats(statsData)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [playerId])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!profile) return null

  return (
    <div className="space-y-6">
      <PlayerCard player={profile} linkTo={false} />

      {/* Avatar Stats */}
      {avatarStats.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Avatar Performance</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {avatarStats.map((stat) => (
              <div key={stat.avatar_name} className="bg-bg-surface border border-border rounded-soft p-3 flex items-center gap-3">
                {stat.image_url && (
                  <img src={stat.image_url} alt={stat.avatar_name} className="h-10 w-10 rounded object-cover" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{stat.avatar_name}</p>
                  <p className="text-xs text-text-muted">
                    <span className="text-accent-green">{stat.wins}W</span>
                    {' / '}
                    <span className="text-accent-red">{stat.losses}L</span>
                    {stat.win_rate != null && ` (${(stat.win_rate * 100).toFixed(0)}%)`}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Matches */}
      {profile.recent_matches?.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Recent Matches</h2>
          <div className="space-y-2">
            {profile.recent_matches.map((match) => {
              const isWinner = match.winner_id === playerId
              return (
                <div key={match.match_id} className="bg-bg-surface border border-border rounded-soft p-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${isWinner ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'}`}>
                      {isWinner ? 'W' : 'L'}
                    </span>
                    <span className="text-sm">
                      vs{' '}
                      <Link
                        to={`/player/${isWinner ? match.loser_id : match.winner_id}`}
                        className="text-primary hover:text-primary-light"
                      >
                        {isWinner ? match.loser_name : match.winner_name}
                      </Link>
                    </span>
                  </div>
                  <span className={`text-sm font-medium ${isWinner ? 'text-accent-green' : 'text-accent-red'}`}>
                    {isWinner ? `+${match.winner_elo_change}` : `${match.loser_elo_change}`}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
