import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import Spinner from '@/components/ui/Spinner'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'

function getWinRateColor(rate) {
  if (rate >= 60) return '#22c55e'
  if (rate >= 50) return '#a3e635'
  if (rate >= 40) return '#facc15'
  return '#ef4444'
}

function DeckLinks({ deckUrl, hasDeckJson, matchId, playerId, label }) {
  const url = deckUrl && deckUrl !== 'No URL provided' && deckUrl !== 'Admin reported match' ? deckUrl : null
  return (
    <span className="flex items-center gap-2">
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline text-xs">
          {label}
        </a>
      ) : '-'}
      {hasDeckJson && (
        <>
          {url && <span className="text-text-muted">|</span>}
          <Link to={`/deck-snapshot/${matchId}/${playerId}`} className="text-secondary hover:underline text-xs">
            Snapshot
          </Link>
        </>
      )}
    </span>
  )
}

function MatchRow({ match }) {
  const date = match.timestamp ? new Date(match.timestamp).toLocaleDateString() : '—'
  const isWin = match.result === 'win'

  return (
    <tr className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
      <td className="px-3 py-2 text-xs text-text-muted">{match.match_id}</td>
      <td className="px-3 py-2">
        <span className={`text-xs font-bold px-2 py-0.5 rounded ${isWin ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'}`}>
          {isWin ? 'W' : 'L'}
        </span>
      </td>
      <td className="px-3 py-2 text-sm">
        <Link to={`/player/${match.player_id}`} className="text-primary hover:underline">
          {match.player_name}
        </Link>
        <span className="text-text-muted text-xs ml-1">({match.player_elo})</span>
      </td>
      <td className="px-3 py-2 text-sm">
        <Link to={`/player/${match.opponent_id}`} className="text-primary hover:underline">
          {match.opponent_name}
        </Link>
        <span className="text-text-muted text-xs ml-1">({match.opponent_elo})</span>
        {match.opponent_avatar && (
          <span className="text-text-muted text-xs ml-1">- {match.opponent_avatar}</span>
        )}
      </td>
      <td className="px-3 py-2 text-center text-xs text-text-muted">
        {match.went_first === true ? 'Play' : match.went_first === false ? 'Draw' : '—'}
      </td>
      <td className="px-3 py-2 text-center text-xs">
        {match.elo_change != null ? (
          <span className={match.elo_change >= 0 ? 'text-accent-green' : 'text-accent-red'}>
            {match.elo_change >= 0 ? '+' : ''}{match.elo_change}
          </span>
        ) : '—'}
      </td>
      <td className="px-3 py-2 text-xs text-text-muted">{date}</td>
      <td className="px-3 py-2">
        <DeckLinks
          deckUrl={match.player_deck_url}
          hasDeckJson={!!match.player_deck_json}
          matchId={match.match_id}
          playerId={match.player_id}
          label="Curiosa"
        />
      </td>
      <td className="px-3 py-2">
        <DeckLinks
          deckUrl={match.opponent_deck_url}
          hasDeckJson={!!match.opponent_deck_json}
          matchId={match.match_id}
          playerId={match.opponent_id}
          label="Curiosa"
        />
      </td>
    </tr>
  )
}

export default function EloBreakdownMatches() {
  const [searchParams] = useSearchParams()
  const avatar = searchParams.get('avatar') || ''
  const bracket = parseInt(searchParams.get('bracket') || '0', 10)
  const source = searchParams.get('source') || 'discord'

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  usePageTitle(`${avatar} ${bracket}-${bracket + 99} ELO Matches`)

  useEffect(() => {
    setLoading(true)
    get(`/api/avatars/elo-breakdown/matches?avatar=${encodeURIComponent(avatar)}&bracket=${bracket}&source=${source}`)
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [avatar, bracket, source])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data?.matches?.length) return (
    <div className="space-y-4">
      <Link to="/avatars" className="text-sm text-secondary hover:underline">&larr; Back to Avatars</Link>
      <p className="text-text-muted text-center py-8">No matches found.</p>
    </div>
  )

  const wins = data.matches.filter(m => m.result === 'win').length
  const total = data.matches.length
  const winRate = total > 0 ? (wins / total * 100).toFixed(1) : 0

  return (
    <div className="space-y-6">
      <Link to="/avatars" className="text-sm text-secondary hover:underline">&larr; Back to Avatars</Link>

      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <h1 className="text-2xl font-display text-text-primary">
          {avatar} — {bracket}-{bracket + 99} ELO Bracket
        </h1>
        <p className="text-sm text-text-muted mt-1">
          {total} matches — <span style={{ color: getWinRateColor(parseFloat(winRate)) }} className="font-bold">{winRate}%</span> win rate
          ({wins}W / {total - wins}L)
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">ID</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Result</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Player</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Opponent</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">Play/Draw</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">ELO</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Date</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Player Deck</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Opp Deck</th>
            </tr>
          </thead>
          <tbody>
            {data.matches.map(match => (
              <MatchRow
                key={`${match.match_id}-${match.result}`}
                match={match}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
