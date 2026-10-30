import { Link } from 'react-router-dom'
import PlayerPicker from '@/components/admin/PlayerPicker'
import { assignPaperResult, clearPaperResult } from '@/api/paperFinishes'
import { resetPaperFinishesCache } from '@/components/player/PaperFinishes'

/**
 * Under a player's name in an event's Top 8: a link to the Summit profile
 * this result matched, and for admins the controls to set or change it.
 */
export default function Top8Profile({ entry, deckId, folder, isAdmin, onChange }) {
  const player = entry?.player
  const status = entry?.status
  const canEdit = isAdmin && deckId

  const run = async (call) => {
    try {
      await call()
      resetPaperFinishesCache()
    } finally {
      onChange?.()
    }
  }

  if (!player && !canEdit) return null

  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
      {player && (
        <Link
          to={`/player/${player.user_id}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-secondary/40 text-secondary hover:border-secondary"
          title="Summit profile"
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" aria-hidden="true">
            <path d="M2 20 L12 4 L22 20 Z" />
          </svg>
          {player.name}
        </Link>
      )}
      {canEdit && (
        <>
          <PlayerPicker
            label={player ? 'Change' : 'Set profile'}
            buttonClassName="text-xs"
            onPick={(p) => run(() => assignPaperResult(folder, deckId, p.user_id))}
          />
          {player && status !== 'assigned' && (
            <button
              type="button"
              className="px-2.5 py-1 rounded-lg border border-border text-text-muted hover:border-accent-red"
              onClick={() => run(() => assignPaperResult(folder, deckId, ''))}
            >
              Not them
            </button>
          )}
          {(status === 'assigned' || status === 'nobody') && (
            <button
              type="button"
              className="px-2.5 py-1 rounded-lg border border-border text-text-muted hover:border-accent-red"
              onClick={() => run(() => clearPaperResult(folder, deckId))}
            >
              Undo
            </button>
          )}
        </>
      )}
    </div>
  )
}
