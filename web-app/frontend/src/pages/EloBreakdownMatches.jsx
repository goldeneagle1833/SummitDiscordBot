import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import Spinner from '@/components/ui/Spinner'
import DeckVisualizer from '@/components/deck/DeckVisualizer'
import { get } from '@/api/client'
import usePageTitle from '@/hooks/usePageTitle'

function getWinRateColor(rate) {
  if (rate >= 60) return '#22c55e'
  if (rate >= 50) return '#a3e635'
  if (rate >= 40) return '#facc15'
  return '#ef4444'
}

function MatchRow({ match, expanded, onToggle }) {
  const date = match.timestamp ? new Date(match.timestamp).toLocaleDateString() : '—'
  const isWin = match.result === 'win'

  let playerDeck = null
  let opponentDeck = null
  try { if (match.player_deck_json) playerDeck = JSON.parse(match.player_deck_json) } catch {}
  try { if (match.opponent_deck_json) opponentDeck = JSON.parse(match.opponent_deck_json) } catch {}

  return (
    <>
      <tr
        className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-3 py-2 text-xs text-text-muted">{match.match_id}</td>
        <td className="px-3 py-2">
          <span className={`text-xs font-bold px-2 py-0.5 rounded ${isWin ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'}`}>
            {isWin ? 'W' : 'L'}
          </span>
        </td>
        <td className="px-3 py-2 text-sm">
          <Link to={`/player/${match.player_id}`} className="text-primary hover:underline" onClick={e => e.stopPropagation()}>
            {match.player_name}
          </Link>
          <span className="text-text-muted text-xs ml-1">({match.player_elo})</span>
        </td>
        <td className="px-3 py-2 text-sm">
          <Link to={`/player/${match.opponent_id}`} className="text-primary hover:underline" onClick={e => e.stopPropagation()}>
            {match.opponent_name}
          </Link>
          <span className="text-text-muted text-xs ml-1">({match.opponent_elo})</span>
          {match.opponent_avatar && (
            <span className="text-text-muted text-xs ml-1">- {match.opponent_avatar}</span>
          )}
        </td>
        <td className="px-3 py-2 text-center text-xs">
          {match.player_life != null && match.opponent_life != null ? (
            <span>
              <span className={isWin ? 'text-accent-green' : 'text-accent-red'}>{match.player_life}</span>
              {' / '}
              <span className={isWin ? 'text-accent-red' : 'text-accent-green'}>{match.opponent_life}</span>
            </span>
          ) : '—'}
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
        <td className="px-3 py-2 text-center text-xs">
          <span className="text-text-muted">{expanded ? '▲' : '▼'}</span>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/50">
          <td colSpan={9} className="p-4 bg-bg-elevated/30">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Player deck */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <h4 className="text-sm font-bold text-text-primary">
                    {match.player_name}'s Deck
                    {match.player_avatar && <span className="text-text-muted font-normal"> — {match.player_avatar}</span>}
                  </h4>
                  {match.player_deck_url && (
                    <a href={match.player_deck_url} target="_blank" rel="noopener noreferrer"
                       className="text-xs text-secondary hover:underline" onClick={e => e.stopPropagation()}>
                      Curiosa ↗
                    </a>
                  )}
                </div>
                {playerDeck ? (
                  <DeckVisualizer spellbook={playerDeck.spellbook} atlas={playerDeck.atlas} sideboard={playerDeck.sideboard} />
                ) : (
                  <p className="text-text-muted text-sm">No deck snapshot available</p>
                )}
              </div>
              {/* Opponent deck */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <h4 className="text-sm font-bold text-text-primary">
                    {match.opponent_name}'s Deck
                    {match.opponent_avatar && <span className="text-text-muted font-normal"> — {match.opponent_avatar}</span>}
                  </h4>
                  {match.opponent_deck_url && (
                    <a href={match.opponent_deck_url} target="_blank" rel="noopener noreferrer"
                       className="text-xs text-secondary hover:underline" onClick={e => e.stopPropagation()}>
                      Curiosa ↗
                    </a>
                  )}
                </div>
                {opponentDeck ? (
                  <DeckVisualizer spellbook={opponentDeck.spellbook} atlas={opponentDeck.atlas} sideboard={opponentDeck.sideboard} />
                ) : (
                  <p className="text-text-muted text-sm">No deck snapshot available</p>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
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
  const [expandedId, setExpandedId] = useState(null)

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
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">Life</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">Play/Draw</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">ELO</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Date</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase"></th>
            </tr>
          </thead>
          <tbody>
            {data.matches.map(match => (
              <MatchRow
                key={`${match.match_id}-${match.result}`}
                match={match}
                expanded={expandedId === `${match.match_id}-${match.result}`}
                onToggle={() => setExpandedId(
                  expandedId === `${match.match_id}-${match.result}` ? null : `${match.match_id}-${match.result}`
                )}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
