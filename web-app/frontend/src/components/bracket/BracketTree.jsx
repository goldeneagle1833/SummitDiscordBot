import { useState } from 'react'
import MatchCard from './MatchCard'

/**
 * The rounds laid out left to right. Each round has half the matches of the
 * one before, so spacing doubles to keep every match beside its feeders.
 */
export default function BracketTree({
  rounds,
  onReport,
  onConfirm,
  onOpenTable,
  onAdminAction,
  isAdmin,
  onSwap,
  avatars = {},
}) {
  const [hoverSeed, setHoverSeed] = useState(null)
  const [pinnedSeed, setPinnedSeed] = useState(null)
  const followSeed = pinnedSeed ?? hoverSeed

  const follow = (kind, seed) => {
    if (kind === 'hover') setHoverSeed(seed)
    else setPinnedSeed((current) => (String(current) === String(seed) ? null : seed))
  }

  if (!rounds?.length) {
    return <p className="text-text-muted text-center py-8">This bracket has no matches yet.</p>
  }

  const pinnedName = pinnedSeed == null
    ? null
    : rounds
        .flatMap((r) => r.matches)
        .flatMap((m) => [
          [m.p1_seed, m.p1_name],
          [m.p2_seed, m.p2_name],
        ])
        .find(([seed, name]) => name && String(seed) === String(pinnedSeed))?.[1]

  return (
    <div className="overflow-x-auto pb-4">
      {!onSwap && (
        <p className="mb-3 text-[11px] text-text-muted">
          {pinnedName ? (
            <>
              Following <span className="text-primary font-semibold">{pinnedName}</span>
              {' · '}
              <button
                type="button"
                onClick={() => setPinnedSeed(null)}
                className="underline hover:text-text-primary"
              >
                clear
              </button>
            </>
          ) : (
            'Hover or tap a player to follow their path.'
          )}
        </p>
      )}
      <div className="flex gap-6 min-w-max">
        {rounds.map((round, roundIndex) => {
          const played = round.matches.filter(
            (m) => m.state === 'complete' || m.state === 'bye',
          ).length

          return (
            <div key={round.round} className="flex flex-col">
              <div className="mb-3 flex items-baseline justify-between gap-2 border-b border-border pb-1.5">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-primary">
                  {round.title}
                </h3>
                <p className="text-[10px] font-mono tabular-nums text-text-muted">
                  {played}/{round.matches.length} done
                </p>
              </div>
              <div
                className="flex flex-col justify-around flex-1"
                style={{ gap: `${roundIndex * 1.5 + 0.75}rem` }}
              >
                {round.matches.map((match) => (
                  <MatchCard
                    key={match.match_no}
                    match={match}
                    onReport={onReport}
                    onConfirm={onConfirm}
                    onOpenTable={onOpenTable}
                    onAdminAction={onAdminAction}
                    isAdmin={isAdmin}
                    onSwap={onSwap}
                    avatars={avatars}
                    followSeed={onSwap ? null : followSeed}
                    onFollow={follow}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
