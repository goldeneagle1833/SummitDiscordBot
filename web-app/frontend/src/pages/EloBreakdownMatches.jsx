import { useState, useEffect, useMemo } from 'react'
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

const ELEMENT_IMG = '/static/images/elements/'
const ELEMENT_FILE = {
  Earth: 'earth.png',
  Fire: 'fire.png',
  Water: 'water.png',
  Air: 'wind.png',
  Void: 'void.png',
}

function ElementIcons({ elements }) {
  if (!elements?.length) return <span className="text-text-muted text-xs">-</span>
  return (
    <span className="flex gap-0.5">
      {elements.map(el => {
        const file = ELEMENT_FILE[el]
        if (!file) return <span key={el} className="text-xs">{el}</span>
        return <img key={el} src={`${ELEMENT_IMG}${file}`} alt={el} title={el} className="w-4 h-4" />
      })}
    </span>
  )
}

function extractElements(deckJson) {
  if (!deckJson) return []
  try {
    const deck = JSON.parse(deckJson)
    const elems = new Set()
    for (const section of ['spellbook', 'sideboard']) {
      for (const card of deck[section] || []) {
        const str = card.elements || ''
        for (const e of str.split(',')) {
          const trimmed = e.trim()
          if (trimmed && trimmed !== 'None') elems.add(trimmed)
        }
      }
    }
    return [...elems].sort()
  } catch { return [] }
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
  const playerElements = useMemo(() => extractElements(match.player_deck_json), [match.player_deck_json])
  const opponentElements = useMemo(() => extractElements(match.opponent_deck_json), [match.opponent_deck_json])

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
        <ElementIcons elements={playerElements} />
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
      <td className="px-3 py-2">
        <DeckLinks
          deckUrl={match.opponent_deck_url}
          hasDeckJson={!!match.opponent_deck_json}
          matchId={match.match_id}
          playerId={match.opponent_id}
          label="Curiosa"
        />
      </td>
      <td className="px-3 py-2">
        <ElementIcons elements={opponentElements} />
      </td>
      <td className="px-3 py-2 text-center text-xs text-text-muted">
        {match.went_first === true ? 'Play' : match.went_first === false ? 'Draw' : '—'}
      </td>
      <td className="px-3 py-2 text-xs text-text-muted">{date}</td>
      <td className="px-3 py-2 text-center text-xs">
        {match.elo_change != null ? (
          <span className={match.elo_change >= 0 ? 'text-accent-green' : 'text-accent-red'}>
            {match.elo_change >= 0 ? '+' : ''}{match.elo_change}
          </span>
        ) : '—'}
      </td>
    </tr>
  )
}

function OpponentEloBreakdown({ matches }) {
  const breakdown = useMemo(() => {
    const buckets = {}
    for (const m of matches) {
      if (m.opponent_elo == null) continue
      const brk = Math.floor(m.opponent_elo / 100) * 100
      if (!buckets[brk]) buckets[brk] = { wins: 0, losses: 0 }
      if (m.result === 'win') buckets[brk].wins++
      else buckets[brk].losses++
    }
    const brackets = Object.keys(buckets).map(Number).sort((a, b) => a - b)
    return { brackets, buckets }
  }, [matches])

  if (!breakdown.brackets.length) return null

  const { brackets, buckets } = breakdown

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-5">
      <h2 className="text-lg font-display text-text-primary mb-4">Win Rate vs Opponent ELO</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Opponent ELO</th>
              {brackets.map(b => (
                <th key={b} className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase whitespace-nowrap">
                  {b}-{b + 99}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-border/50">
              <td className="px-3 py-2 text-xs font-bold text-text-muted">Win Rate</td>
              {brackets.map(b => {
                const d = buckets[b]
                const total = d.wins + d.losses
                const wr = total > 0 ? (d.wins / total * 100).toFixed(1) : null
                return (
                  <td key={b} className="px-3 py-2 text-center whitespace-nowrap">
                    {wr != null ? (
                      <>
                        <span className="font-bold" style={{ color: getWinRateColor(parseFloat(wr)) }}>
                          {wr}%
                        </span>
                        <div className="text-xs text-text-muted">({total})</div>
                      </>
                    ) : '—'}
                  </td>
                )
              })}
            </tr>
            <tr className="border-b border-border/50">
              <td className="px-3 py-2 text-xs font-bold text-text-muted">Record</td>
              {brackets.map(b => {
                const d = buckets[b]
                return (
                  <td key={b} className="px-3 py-2 text-center text-xs text-text-muted whitespace-nowrap">
                    {d.wins}W / {d.losses}L
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
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

      <OpponentEloBreakdown matches={data.matches} />

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">ID</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Result</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Player</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Player Deck</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Elements</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Opponent</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Opp Deck</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Elements</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">Play/Draw</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">Date</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">ELO</th>
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
