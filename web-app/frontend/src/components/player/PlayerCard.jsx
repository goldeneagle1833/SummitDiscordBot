import { Link } from 'react-router-dom'
import Avatar from '@/components/ui/Avatar'
import Badge from '@/components/ui/Badge'

export default function PlayerCard({ player, linkTo = true }) {
  const content = (
    <div className="flex items-center gap-4 p-4 bg-bg-surface rounded-soft border border-border">
      <Avatar src={player.avatar_url} alt={player.display_name} size="lg" />
      <div className="flex-1 min-w-0">
        <h3 className="text-lg font-semibold truncate">{player.display_name}</h3>
        <div className="flex flex-wrap items-center gap-2 mt-1">
          {player.rank && <Badge variant="secondary">#{player.rank}</Badge>}
          <span className="text-sm text-text-muted">ELO: {player.elo}</span>
        </div>
        <div className="flex items-center gap-3 mt-1 text-sm">
          <span className="text-accent-green">{player.wins}W</span>
          <span className="text-accent-red">{player.losses}L</span>
          {player.win_rate != null && (
            <span className="text-text-muted">
              {(player.win_rate * 100).toFixed(1)}%
            </span>
          )}
        </div>
      </div>
    </div>
  )

  if (linkTo && player.player_id) {
    return (
      <Link to={`/player/${player.player_id}`} className="block hover:ring-1 hover:ring-primary/50 rounded-soft transition-all">
        {content}
      </Link>
    )
  }

  return content
}
