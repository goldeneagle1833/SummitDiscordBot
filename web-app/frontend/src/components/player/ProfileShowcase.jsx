import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getShowcase } from '@/api/players'
import { cardImageUrl } from '@/api/articles'

/**
 * The player's own boxes on their profile card, beside the featured deck:
 * a short bio, a favorite card and a rival. Visitors only ever see what
 * the player filled in; the owner gets a small prompt for each empty one.
 */
export function useShowcase(playerId, refreshKey = 0) {
  const [showcase, setShowcase] = useState(null)
  useEffect(() => {
    let active = true
    getShowcase(playerId)
      .then((res) => active && setShowcase(res || {}))
      .catch(() => active && setShowcase({}))
    return () => {
      active = false
    }
  }, [playerId, refreshKey])
  return showcase
}

const TILE = 'w-full min-h-[170px] rounded-xl border border-border bg-bg-raised overflow-hidden relative'

function EditButton({ onClick, label }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="absolute top-3 right-3 z-10 h-8 px-3 rounded-lg border border-white/20 bg-black/60 text-xs text-gray-200 hover:border-secondary hover:text-secondary"
    >
      Edit
    </button>
  )
}

/** The owner's prompt for a box they have not filled in (visitors see nothing). */
function EmptyBox({ title, text, action, onEdit }) {
  return (
    <section
      aria-label={title}
      className="w-full rounded-xl border border-dashed border-border bg-bg-raised p-4 flex flex-col gap-3"
    >
      <div>
        <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">{title}</h2>
        <p className="text-sm text-text-muted mt-1">{text}</p>
      </div>
      <button
        type="button"
        onClick={onEdit}
        className="self-start h-9 px-3 text-sm font-semibold rounded-lg bg-secondary text-black hover:opacity-90"
      >
        {action}
      </button>
    </section>
  )
}

export function FavoriteCardBox({ card, isOwner, onEdit }) {
  if (!card) {
    if (!isOwner) return null
    return (
      <EmptyBox
        title="Favorite Card"
        text="Show off the card you love most. Search for any Sorcery card."
        action="Pick a card"
        onEdit={onEdit}
      />
    )
  }
  const image = cardImageUrl(card.image)
  return (
    <section aria-label="Favorite card" className="relative">
      {isOwner && <EditButton onClick={onEdit} label="Edit favorite card" />}
      <Link
        to={`/card/${encodeURIComponent(card.name)}`}
        className={`${TILE} group flex hover:border-secondary/60 transition-colors`}
      >
        {image && (
          <>
            <div
              aria-hidden="true"
              className="absolute inset-0 bg-cover opacity-40 blur-[2px] scale-110"
              style={{ backgroundImage: `url('${image}')`, backgroundPosition: '50% 25%' }}
            />
            <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-r from-black/90 via-black/70 to-black/40" />
          </>
        )}
        <div className="relative flex gap-4 p-4 w-full" style={{ textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>
          {image && (
            <img
              src={image}
              alt=""
              loading="lazy"
              className="w-[96px] h-[134px] object-cover rounded-md shadow-lg shrink-0 self-center"
            />
          )}
          <div className="min-w-0 flex flex-col">
            <div className="text-xs font-bold uppercase tracking-wider text-gray-300 pr-14">Favorite Card</div>
            <h3 className="text-xl font-bold text-white leading-tight mt-1 break-words">{card.name}</h3>
            <span className="mt-auto pt-4 text-sm font-semibold text-secondary">Card stats &rarr;</span>
          </div>
        </div>
      </Link>
    </section>
  )
}

function initials(name) {
  const parts = String(name || '?').replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/)
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] || '?').slice(0, 2)).toUpperCase()
}

function RivalPicture({ rival }) {
  const [failed, setFailed] = useState(false)
  const frame = 'w-14 h-14 shrink-0 rounded-full border-2 border-accent-red/70 bg-bg-surface'
  if (rival.avatar_url && !failed) {
    return <img src={rival.avatar_url} alt="" className={`${frame} object-cover`} onError={() => setFailed(true)} />
  }
  return (
    <div aria-hidden="true" className={`${frame} flex items-center justify-center font-display text-lg text-accent-red`}>
      {initials(rival.name)}
    </div>
  )
}

/** The player they picked as their rival, with their head-to-head record. */
export function RivalBox({ rival, isOwner, onEdit }) {
  if (!rival) {
    if (!isOwner) return null
    return (
      <EmptyBox
        title="Rival"
        text="Pick someone you've played. Your head-to-head record shows here."
        action="Pick a rival"
        onEdit={onEdit}
      />
    )
  }
  const games = rival.wins + rival.losses
  const ahead = rival.wins > rival.losses ? 'text-accent-green' : rival.wins < rival.losses ? 'text-accent-red' : 'text-text-primary'
  return (
    <section aria-label="Rival" className="relative">
      {isOwner && <EditButton onClick={onEdit} label="Edit rival" />}
      <Link
        to={`/player/${rival.id}`}
        className={`${TILE} p-4 flex flex-col hover:border-secondary/60 transition-colors`}
      >
        <div className="text-xs font-bold uppercase tracking-wider text-text-muted pr-14">Rival</div>
        <div className="flex items-center gap-3 mt-3">
          <RivalPicture rival={rival} />
          <h3 className="text-xl font-bold text-text-primary leading-tight break-words min-w-0">{rival.name}</h3>
        </div>
        <div className="mt-auto pt-4 flex items-end justify-between gap-3">
          <div>
            <div className={`text-3xl font-extrabold tabular-nums leading-none ${ahead}`}>
              {rival.wins}<span className="text-text-muted mx-1">–</span>{rival.losses}
            </div>
            <div className="text-sm text-text-muted mt-1">
              Head to head{games > 0 ? ` · ${games} game${games === 1 ? '' : 's'}` : ''}
            </div>
          </div>
          <span className="text-sm font-semibold text-secondary">Profile &rarr;</span>
        </div>
      </Link>
    </section>
  )
}

/** The player's short description under their name. Nothing at all for visitors when it is empty. */
export function ProfileBio({ bio, isOwner, onEdit }) {
  if (!bio) {
    if (!isOwner) return null
    return (
      <button
        type="button"
        onClick={onEdit}
        className="self-start text-sm text-text-muted hover:text-secondary underline decoration-dotted underline-offset-4"
      >
        + Add a short description
      </button>
    )
  }
  return (
    <p className="text-sm sm:text-base text-text-secondary max-w-xl break-words whitespace-pre-line">
      {bio}
      {isOwner && (
        <button
          type="button"
          onClick={onEdit}
          className="ml-2 text-xs text-text-muted hover:text-secondary underline"
        >
          Edit
        </button>
      )}
    </p>
  )
}
