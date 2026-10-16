import { useMemo, useState } from 'react'
import AvatarArtCard, { useAvatarArt } from './AvatarArtCard'
import { getWinRateColor } from '@/utils/winRateColor'

const MIN_GAMES = 3

function MatchupList({ title, rows, empty }) {
  return (
    <section className="bg-bg-surface border border-border rounded-xl p-5">
      <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted mb-4">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-text-muted">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((m) => (
            <li key={m.opponent_avatar} className="flex items-center justify-between gap-3">
              <span className="font-semibold text-text-primary truncate">{m.opponent_avatar}</span>
              <span className="text-sm text-text-muted tabular-nums shrink-0">
                {m.wins}-{m.losses}
                <strong className="ml-3 text-base" style={{ color: getWinRateColor(m.win_rate) }}>{m.win_rate}%</strong>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/**
 * The Matchups tab: how the player does against each opposing avatar, for all
 * their avatars together or for one avatar they were on.
 */
export default function AvatarMatchups({ matchups, byAvatar = {}, myAvatars = [] }) {
  const { imageFiles } = useAvatarArt()
  const [playingAs, setPlayingAs] = useState('all')
  const options = (myAvatars.length ? myAvatars : Object.keys(byAvatar)).filter((name) => byAvatar[name]?.length)
  const rows = useMemo(
    () => (playingAs === 'all' ? matchups : byAvatar[playingAs]) || [],
    [playingAs, matchups, byAvatar],
  )

  if (!matchups?.length) return null

  const rated = rows.filter((m) => m.total_games >= MIN_GAMES)
  const best = [...rated].filter((m) => m.win_rate > 50).sort((a, b) => b.win_rate - a.win_rate || b.total_games - a.total_games).slice(0, 5)
  const worst = [...rated].filter((m) => m.win_rate < 50).sort((a, b) => a.win_rate - b.win_rate || b.total_games - a.total_games).slice(0, 5)
  const total = rows.reduce((n, m) => n + m.total_games, 0)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Against other avatars</h2>
        {options.length > 1 && (
          <div className="flex items-center gap-2">
            <label htmlFor="matchup-playing-as" className="text-sm text-text-muted">Playing as</label>
            <select
              id="matchup-playing-as"
              value={playingAs}
              onChange={(e) => setPlayingAs(e.target.value)}
              className="h-11 rounded-lg border border-border bg-bg-raised px-3 text-sm"
            >
              <option value="all">All my avatars</option>
              {options.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </div>
        )}
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <MatchupList title="Best matchups" rows={best} empty={`No winning matchups with ${MIN_GAMES}+ games yet.`} />
        <MatchupList title="Toughest matchups" rows={worst} empty={`No losing matchups with ${MIN_GAMES}+ games yet.`} />
      </div>

      <ul className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map((m) => (
          <li key={m.opponent_avatar}>
            <AvatarArtCard name={m.opponent_avatar} imageFiles={imageFiles} className="min-h-[150px]">
              <h3 className="font-bold text-white leading-tight">vs {m.opponent_avatar}</h3>
              <div className="mt-auto pt-4">
                <div className="text-3xl font-extrabold tabular-nums leading-none" style={{ color: getWinRateColor(m.win_rate) }}>
                  {m.win_rate}%
                </div>
                <div className="text-sm text-gray-200 mt-1 tabular-nums">
                  {m.wins}W · {m.losses}L
                </div>
              </div>
            </AvatarArtCard>
          </li>
        ))}
      </ul>
      <p className="text-xs text-text-muted">
        {total} games against {rows.length} avatars. Best and toughest need {MIN_GAMES}+ games.
      </p>
    </div>
  )
}
