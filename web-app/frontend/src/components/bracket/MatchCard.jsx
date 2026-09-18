import { Link } from 'react-router-dom'

function Side({
  seed,
  name,
  userId,
  avatar,
  isWinner,
  isLoser,
  reported,
  fromBye,
  linkTo = true,
  dragHandlers,
}) {
  if (!name) {
    return (
      <div
        className="flex items-center gap-2 px-2.5 py-2 text-sm text-text-muted italic"
        {...(dragHandlers?.dropOnly || {})}
      >
        <span className="w-5 h-5 shrink-0 rounded-full border border-dashed border-border" />
        <span className="text-xs">Waiting</span>
      </div>
    )
  }

  return (
    <div
      className={`flex items-center gap-2 px-2.5 py-2 text-sm transition-colors ${
        isWinner ? 'bg-accent-green/5 font-semibold text-text-primary' : ''
      } ${isLoser ? 'text-text-muted' : ''} ${
        dragHandlers ? 'cursor-grab active:cursor-grabbing hover:bg-bg-elevated' : ''
      }`}
      {...(dragHandlers?.props || {})}
    >
      {avatar ? (
        <img
          src={avatar}
          alt=""
          loading="lazy"
          className={`w-5 h-5 shrink-0 rounded-full object-cover ${isLoser ? 'grayscale opacity-60' : ''}`}
          onError={(e) => {
            e.target.style.visibility = 'hidden'
          }}
        />
      ) : (
        <span className="w-5 h-5 shrink-0 rounded-full bg-bg-elevated" />
      )}

      <span
        className={`w-5 shrink-0 text-[10px] text-center rounded bg-bg-raised text-text-muted ${
          isWinner ? 'text-text-primary' : ''
        }`}
      >
        {seed}
      </span>

      {userId && linkTo ? (
        <Link
          to={`/player/${userId}`}
          className={`truncate hover:text-primary transition-colors ${isLoser ? 'line-through decoration-1' : ''}`}
        >
          {name}
        </Link>
      ) : (
        <span className={`truncate ${isLoser ? 'line-through decoration-1' : ''}`}>{name}</span>
      )}

      {fromBye && (
        <span
          className="text-[10px] uppercase tracking-wide text-text-muted"
          title="Advanced on a first-round bye"
        >
          bye
        </span>
      )}
      {reported && <span className="ml-auto text-xs text-amber-400">reported</span>}
      {isWinner && !reported && <span className="ml-auto text-xs text-accent-green">W</span>}
    </div>
  )
}

/**
 * One slot in the tree. Shows both seats, who won, and - for the two players
 * involved - the buttons to settle it.
 *
 * With `onSwap` the two names become draggable: dropping one on another swaps
 * their seeds, which is how the admin arranges a draft before publishing.
 */
export default function MatchCard({
  match,
  onReport,
  onConfirm,
  onAdminAction,
  isAdmin,
  onSwap,
  avatars = {},
}) {
  const complete = match.state === 'complete' || match.state === 'bye'
  const reportedWinner = match.state === 'reported' ? match.reported_winner_id : null
  const needsViewer = match.viewer_can_report || match.viewer_can_confirm

  const p1Wins = complete && String(match.winner_seed) === String(match.p1_seed)
  const p2Wins = complete && String(match.winner_seed) === String(match.p2_seed)

  const dragFor = (seed) => {
    if (!onSwap || !seed) return null
    return {
      props: {
        draggable: true,
        onDragStart: (e) => {
          e.dataTransfer.setData('text/plain', String(seed))
          e.dataTransfer.effectAllowed = 'move'
        },
        onDragOver: (e) => {
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
        },
        onDrop: (e) => {
          e.preventDefault()
          e.stopPropagation()
          const from = Number(e.dataTransfer.getData('text/plain'))
          if (from && from !== seed) onSwap(from, seed)
        },
      },
    }
  }

  return (
    <div
      className={`bg-bg-surface border rounded-soft overflow-hidden w-60 transition-shadow ${
        needsViewer
          ? 'border-secondary shadow-[0_0_0_1px_rgba(212,175,55,0.35)]'
          : match.playable && !complete
            ? 'border-border hover:border-text-muted'
            : 'border-border'
      }`}
    >
      <Side
        seed={match.p1_seed}
        name={match.p1_name}
        userId={match.p1_user_id}
        avatar={avatars[String(match.p1_user_id)]}
        isWinner={p1Wins}
        isLoser={complete && !p1Wins && !!match.p2_name}
        reported={reportedWinner && String(reportedWinner) === String(match.p1_user_id)}
        fromBye={match.p1_from_bye}
        linkTo={!onSwap}
        dragHandlers={dragFor(match.p1_seed)}
      />
      <div className="border-t border-border" />
      <Side
        seed={match.p2_seed}
        name={match.p2_name}
        userId={match.p2_user_id}
        avatar={avatars[String(match.p2_user_id)]}
        isWinner={p2Wins}
        isLoser={complete && !p2Wins && !!match.p1_name}
        reported={reportedWinner && String(reportedWinner) === String(match.p2_user_id)}
        fromBye={match.p2_from_bye}
        linkTo={!onSwap}
        dragHandlers={dragFor(match.p2_seed)}
      />

      {match.viewer_can_report && (
        <button
          onClick={() => onReport(match)}
          className="w-full px-3 py-1.5 text-xs font-medium bg-secondary text-black hover:bg-secondary-dark transition-colors"
        >
          Report result
        </button>
      )}

      {match.viewer_can_confirm && (
        <div className="flex border-t border-border">
          <button
            onClick={() => onConfirm(match, true)}
            className="flex-1 px-2 py-1.5 text-xs font-medium text-accent-green hover:bg-accent-green/10 transition-colors"
          >
            Confirm
          </button>
          <button
            onClick={() => onConfirm(match, false)}
            className="flex-1 px-2 py-1.5 text-xs font-medium text-accent-red hover:bg-accent-red/10 transition-colors border-l border-border"
          >
            Dispute
          </button>
        </div>
      )}

      {match.state === 'reported' && !match.viewer_can_confirm && (
        <p className="px-3 py-1 text-xs text-amber-400 bg-bg-raised">
          Awaiting confirmation
        </p>
      )}

      {isAdmin && onAdminAction && match.playable && (
        <div className="flex border-t border-border text-xs">
          {!complete && (
            <>
              <button
                onClick={() => onAdminAction('result', match, match.p1_user_id)}
                className="flex-1 px-1 py-1 text-text-muted hover:text-text-primary"
                title={`Give the win to ${match.p1_name}`}
              >
                ▲ win
              </button>
              <button
                onClick={() => onAdminAction('result', match, match.p2_user_id)}
                className="flex-1 px-1 py-1 text-text-muted hover:text-text-primary border-l border-border"
                title={`Give the win to ${match.p2_name}`}
              >
                ▼ win
              </button>
            </>
          )}
          {complete && (
            <button
              onClick={() => onAdminAction('reset', match)}
              className="flex-1 px-1 py-1 text-accent-red hover:bg-accent-red/10"
            >
              Reset
            </button>
          )}
        </div>
      )}
    </div>
  )
}
