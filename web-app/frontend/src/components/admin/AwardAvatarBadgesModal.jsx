import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  awardEventAvatarBadges,
  previewEventAvatarBadges,
  undoEventAvatarBadges,
} from '@/api/paperFinishes'
import { resetEventAvatarBadgesCache, FoilCard } from '@/components/player/EventAvatarBadges'

const NO_ACCOUNT = {
  unmatched: 'No Summit account found',
  ambiguous: 'Name matches more than one account',
  short_name: 'Name too short to match on its own',
  shared_uploader: 'Deck posted by an organiser',
  nobody: 'Set to nobody',
}

function record(a) {
  if (a.wins == null) return null
  return `${a.wins}-${a.losses}${a.draws ? `-${a.draws}` : ''}`
}

/**
 * Admin only, from an event's Top 8 page: shows who is the best finisher on
 * each avatar in the whole field, then awards "Top <avatar>" badges to those
 * with a Summit account. Awarding again replaces the event's badges.
 */
export default function AwardAvatarBadgesModal({ folder, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  // Avatars ticked to receive a badge. Events have different prize rules, so
  // the admin picks; starts as what is awarded now, or every eligible avatar.
  const [picked, setPicked] = useState(new Set())

  const resetPicked = (res) => {
    const eligible = (res?.avatars || []).filter((a) => a.player)
    const current = res?.awarded || []
    setPicked(new Set(
      current.length
        ? eligible.filter((a) => current.some((b) => b.avatar === a.avatar)).map((a) => a.avatar)
        : eligible.map((a) => a.avatar),
    ))
  }

  const load = () => {
    setError(null)
    previewEventAvatarBadges(folder)
      .then((res) => { setData(res); resetPicked(res) })
      .catch((err) => setError(err.message || 'Could not load the event'))
  }

  useEffect(load, [folder])

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const run = async (action) => {
    setBusy(true)
    setError(null)
    try {
      if (action === 'award') {
        const res = await awardEventAvatarBadges(folder, [...picked])
        setData(res)
        resetPicked(res)
        setDone(`${res.awarded.length} badge${res.awarded.length === 1 ? '' : 's'} awarded.`)
      } else {
        const res = await undoEventAvatarBadges(folder)
        setDone(`${res.removed} badge${res.removed === 1 ? '' : 's'} removed.`)
        load()
      }
      resetEventAvatarBadgesCache()
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const winners = data?.avatars?.filter((a) => a.player) || []
  const awarded = data?.awarded || []
  const chosen = winners.filter((a) => picked.has(a.avatar))
  const toggle = (avatar) => setPicked((prev) => {
    const next = new Set(prev)
    if (next.has(avatar)) next.delete(avatar)
    else next.add(avatar)
    return next
  })
  const allPicked = winners.length > 0 && chosen.length === winners.length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Award top avatar badges"
        className="bg-bg-surface border border-border rounded-lg w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-border">
          <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <FoilCard size={20} id="modal" /> Top avatar badges
          </h3>
          <p className="text-xs text-text-muted mt-1">
            The best finisher on each avatar earns <strong className="text-text-secondary">Top &lt;avatar&gt; · {data?.event || 'this event'}</strong> on
            their Summit profile. Players without a Summit account get nothing, and nobody else moves up to take their avatar.
          </p>
        </div>

        <div className="p-5 overflow-y-auto flex-1 space-y-3">
          {!data && !error && <p className="text-sm text-text-muted text-center py-6">Loading...</p>}
          {error && <p className="text-sm text-accent-red">{error}</p>}
          {done && <p className="text-sm text-green-400">{done}</p>}

          {data && (
            <>
              <p className="text-xs text-text-muted">
                {data.source === 'standings'
                  ? `Whole field: ${data.field_size} players, from the imported match history (Top 8 in page order).`
                  : 'No match history imported, so only the Top 8 decks count. Import Match History first to include the whole field.'}
                {awarded.length > 0 && ` ${awarded.length} badge${awarded.length === 1 ? ' is' : 's are'} awarded now.`}
              </p>
              {winners.length > 1 && (
                <div className="flex items-center justify-between text-xs text-text-muted">
                  <span>Tick the avatars that get a badge at this event. Unticked ones get none.</span>
                  <button
                    type="button"
                    onClick={() => setPicked(new Set(allPicked ? [] : winners.map((a) => a.avatar)))}
                    className="text-secondary hover:underline"
                  >
                    {allPicked ? 'Untick all' : 'Tick all'}
                  </button>
                </div>
              )}
              {data.avatars.length === 0 ? (
                <p className="text-sm text-text-muted">No decks with an avatar in this event.</p>
              ) : (
                <ul className="divide-y divide-border border border-border rounded-lg">
                  {data.avatars.map((a) => {
                    const isAwarded = awarded.some((b) => b.avatar === a.avatar && b.user_id === a.player?.user_id)
                    return (
                      <li key={a.avatar} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 text-sm">
                        <label className={`flex items-center gap-2 min-w-[8rem] ${a.player ? 'cursor-pointer' : 'opacity-60'}`}>
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-secondary"
                            checked={!!a.player && picked.has(a.avatar)}
                            disabled={!a.player || busy}
                            onChange={() => toggle(a.avatar)}
                            aria-label={`Give the ${a.avatar} badge`}
                          />
                          <strong className="text-text-primary">{a.avatar}</strong>
                        </label>
                        <span className="flex-1 min-w-[10rem]">
                          {a.player ? (
                            <Link to={`/player/${a.player.user_id}`} className="text-secondary hover:underline">
                              {a.player.name}
                            </Link>
                          ) : (
                            <span className="text-text-muted">
                              {a.paper_name || 'Unknown'} · {NO_ACCOUNT[a.status] || 'No Summit account'}
                            </span>
                          )}
                          {isAwarded && <span className="ml-2 text-xs text-green-400">awarded</span>}
                        </span>
                        <span className="text-xs text-text-muted tabular-nums">
                          {[`#${a.place}`, a.finish, record(a), `${a.avatar_players} on it`].filter(Boolean).join(' · ')}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
              {data.avatars.some((a) => !a.player) && (
                <p className="text-xs text-text-muted">
                  To give a badge to someone listed without an account, link their name to their profile (Admin &gt; Paper Tournament Badges, or Set profile on a Top 8 row), then award again.
                </p>
              )}
            </>
          )}
        </div>

        <div className="p-4 border-t border-border flex flex-wrap justify-end gap-2">
          {awarded.length > 0 && (
            <button
              onClick={() => run('undo')}
              disabled={busy}
              className="px-4 py-2 text-sm rounded border border-accent-red/40 text-accent-red hover:bg-accent-red/10 disabled:opacity-50"
            >
              Undo badges
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary"
          >
            Close
          </button>
          <button
            onClick={() => run('award')}
            disabled={busy || !chosen.length}
            className="px-4 py-2 text-sm rounded bg-secondary text-black font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {busy ? 'Working...' : `${awarded.length ? 'Award again' : 'Award'} ${chosen.length} badge${chosen.length === 1 ? '' : 's'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
