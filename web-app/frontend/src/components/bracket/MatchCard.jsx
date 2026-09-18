import { useState } from 'react'
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
  eloChange,
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
      {eloChange != null && !reported && (
        <span
          className={`ml-auto text-[11px] ${eloChange > 0 ? 'text-accent-green' : 'text-accent-red'}`}
          title="Lifetime ELO from this match"
        >
          {eloChange > 0 ? `+${eloChange}` : eloChange}
        </span>
      )}
      {isWinner && !reported && eloChange == null && (
        <span className="ml-auto text-xs text-accent-green">W</span>
      )}
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
  onOpenTable,
  onAdminAction,
  isAdmin,
  onSwap,
  avatars = {},
}) {
  const [replayInput, setReplayInput] = useState(null)
  const complete = match.state === 'complete' || match.state === 'bye'
  const reportedWinner = match.state === 'reported' ? match.reported_winner_id : null
  const needsViewer = match.viewer_can_report || match.viewer_can_confirm

  const p1Wins = complete && String(match.winner_seed) === String(match.p1_seed)
  const p2Wins = complete && String(match.winner_seed) === String(match.p2_seed)

  // Ranked lifetime ELO, shown on the seat it moved.
  const rated = match.elo_applied_at != null
  const p1Elo = rated ? (p1Wins ? match.winner_elo_change : match.loser_elo_change) : null
  const p2Elo = rated ? (p2Wins ? match.winner_elo_change : match.loser_elo_change) : null

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
        eloChange={p1Elo}
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
        eloChange={p2Elo}
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

      {/* Sorcery Online table — only ever shown to the two players */}
      {match.viewer_table_url && (
        <a
          href={match.viewer_table_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block px-3 py-1.5 text-xs font-medium text-center bg-primary/15 text-primary hover:bg-primary/25 transition-colors border-t border-border"
        >
          Join your table
        </a>
      )}

      {!match.viewer_table_url && match.viewer_can_open_table && (
        <button
          onClick={() => onOpenTable?.(match)}
          className="w-full px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors border-t border-border"
        >
          Open table on Sorcery Online
        </button>
      )}

      {match.viewer_is_player && !match.viewer_table_url && match.decks_missing?.length > 0 && (
        <p className="px-3 py-1 text-[11px] text-text-muted bg-bg-raised border-t border-border">
          Table opens once {match.decks_missing.join(' and ')} submit a decklist
        </p>
      )}

      {match.replay_url && (
        <a
          href={match.replay_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block px-3 py-1.5 text-xs text-center text-secondary hover:underline border-t border-border"
        >
          Watch replay
          {!match.replay_public && (
            <span className="text-text-muted"> · hidden until the bracket ends</span>
          )}
        </a>
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
          <button
            onClick={() => setReplayInput(replayInput === null ? (match.replay_url || '') : null)}
            className="flex-1 px-1 py-1 text-text-muted hover:text-text-primary border-l border-border"
          >
            {match.replay_url ? 'Edit replay' : 'Replay'}
          </button>
        </div>
      )}

      {isAdmin && replayInput !== null && (
        <form
          className="px-2 py-2 border-t border-border space-y-1"
          onSubmit={(e) => {
            e.preventDefault()
            onAdminAction('replay', match, replayInput.trim())
            setReplayInput(null)
          }}
        >
          <input
            value={replayInput}
            onChange={(e) => setReplayInput(e.target.value)}
            placeholder="Sorcery Online replay link"
            aria-label={`Replay link for match ${match.match_no}`}
            className="w-full bg-bg-raised border border-border rounded px-2 py-1 text-xs"
          />
          <div className="flex gap-1">
            <button
              type="submit"
              className="flex-1 px-1 py-1 text-xs rounded bg-secondary text-black font-medium"
            >
              Save
            </button>
            {match.replay_url && (
              <button
                type="button"
                onClick={() => {
                  onAdminAction('clear-replay', match)
                  setReplayInput(null)
                }}
                className="px-2 py-1 text-xs text-accent-red"
              >
                Remove
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  )
}
