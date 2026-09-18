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
  if (!rounds?.length) {
    return <p className="text-text-muted text-center py-8">This bracket has no matches yet.</p>
  }

  return (
    <div className="overflow-x-auto pb-4">
      <div className="flex gap-6 min-w-max">
        {rounds.map((round, roundIndex) => {
          const played = round.matches.filter(
            (m) => m.state === 'complete' || m.state === 'bye',
          ).length

          return (
            <div key={round.round} className="flex flex-col">
              <div className="mb-3 text-center">
                <h3 className="text-xs uppercase tracking-wider text-text-muted">{round.title}</h3>
                <p className="text-[10px] text-text-muted/70">
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
