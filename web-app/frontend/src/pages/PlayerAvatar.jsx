import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getPlayerAvatarStats } from '@/api/players'
import Spinner from '@/components/ui/Spinner'
import StatCard from '@/components/player/StatCard'
import CollapsibleSection from '@/components/player/CollapsibleSection'
import usePageTitle from '@/hooks/usePageTitle'

export default function PlayerAvatar() {
  const { playerId, avatarName } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [matchupsOpen, setMatchupsOpen] = useState(true)
  const [historyOpen, setHistoryOpen] = useState(false)

  usePageTitle(data ? `${data.avatar} - ${data.player_name}` : 'Avatar Stats')

  useEffect(() => {
    setLoading(true)
    getPlayerAvatarStats(playerId, decodeURIComponent(avatarName))
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [playerId, avatarName])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  const onPlay = data.on_play || {}
  const onDraw = data.on_draw || {}

  return (
    <div className="space-y-6">
      <Link to={`/player/${playerId}`} className="text-sm text-secondary hover:underline">
        &larr; Back to Profile
      </Link>

      {/* Header */}
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <h1 className="text-2xl font-display text-text-primary">{data.avatar}</h1>
        <p className="text-sm text-text-muted mt-1">
          <Link to={`/player/${playerId}`} className="text-secondary hover:underline">
            {data.player_name}
          </Link>
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Wins" value={<span className="text-accent-green">{data.wins}</span>} />
        <StatCard label="Losses" value={<span className="text-accent-red">{data.losses}</span>} />
        <StatCard label="Win Rate" value={`${data.win_rate}%`} />
        <StatCard label="Total Games" value={data.total} />
        {onPlay.total > 0 && (
          <StatCard
            label="On the Play"
            value={`${onPlay.win_rate}% (${onPlay.wins}/${onPlay.total})`}
          />
        )}
        {onDraw.total > 0 && (
          <StatCard
            label="On the Draw"
            value={`${onDraw.win_rate}% (${onDraw.wins}/${onDraw.total})`}
          />
        )}
      </div>

      {/* Matchups vs Avatars */}
      {data.matchups?.length > 0 && (
        <CollapsibleSection
          title="Matchups vs Avatars"
          open={matchupsOpen}
          onToggle={() => setMatchupsOpen((o) => !o)}
        >
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {data.matchups.map((m) => (
              <div
                key={m.opponent_avatar}
                className="bg-bg-raised border border-border rounded-lg p-3 text-center"
              >
                <p className="font-medium text-text-primary text-sm mb-1">{m.opponent_avatar}</p>
                <p className="text-sm">
                  <span className="text-accent-green">{m.wins}</span>
                  {' - '}
                  <span className="text-accent-red">{m.losses}</span>
                </p>
                <p className="text-xs text-text-muted">{m.win_rate}% ({m.total} games)</p>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Match History */}
      {data.matches?.length > 0 && (
        <CollapsibleSection
          title={`Match History (${data.matches.length})`}
          open={historyOpen}
          onToggle={() => setHistoryOpen((o) => !o)}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted border-b border-border">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Result</th>
                  <th className="pb-2 pr-4">Opponent</th>
                  <th className="pb-2 pr-4">Opp. Avatar</th>
                  <th className="pb-2 pr-4">ELO</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.matches.map((m, i) => (
                  <tr key={m.match_id || i} className="hover:bg-bg-raised transition-colors">
                    <td className="py-2 pr-4 text-text-muted whitespace-nowrap">
                      {m.date ? new Date(m.date).toLocaleDateString() : '-'}
                    </td>
                    <td className={`py-2 pr-4 font-medium ${m.result === 'Win' ? 'text-accent-green' : 'text-accent-red'}`}>
                      {m.result}
                    </td>
                    <td className="py-2 pr-4">
                      {m.opponent_id ? (
                        <Link to={`/player/${m.opponent_id}`} className="text-secondary hover:underline">
                          {m.opponent}
                        </Link>
                      ) : (
                        m.opponent
                      )}
                    </td>
                    <td className="py-2 pr-4 text-text-muted">{m.opponent_avatar}</td>
                    <td className="py-2 pr-4 text-text-muted">
                      {m.elo_change > 0
                        ? <span className="text-accent-green">+{m.elo_change}</span>
                        : m.elo_change < 0
                          ? <span className="text-accent-red">{m.elo_change}</span>
                          : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CollapsibleSection>
      )}

      {data.total === 0 && (
        <p className="text-center text-text-muted py-8">No matches found with this avatar.</p>
      )}
    </div>
  )
}
