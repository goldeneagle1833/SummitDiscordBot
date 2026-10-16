import { useEffect, useRef, useState } from 'react'
import PostseasonName, { useBracketMarks } from '@/components/player/BracketMarks'

function initials(name) {
  const parts = String(name || '?').replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/)
  const text = parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] || '?').slice(0, 2)
  return text.toUpperCase()
}

function ProfilePicture({ name, src }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  const frame = 'w-20 h-20 sm:w-24 sm:h-24 shrink-0 rounded-full border-[3px] border-secondary bg-bg-raised'
  if (src && !failed) {
    return <img src={src} alt="" className={`${frame} object-cover`} onError={() => setFailed(true)} />
  }
  return (
    <div aria-hidden="true" className={`${frame} flex items-center justify-center font-display text-3xl text-secondary`}>
      {initials(name)}
    </div>
  )
}

function BigStat({ value, label, gold = false }) {
  return (
    <div>
      <div className={`text-4xl font-extrabold leading-none tabular-nums ${gold ? 'text-secondary' : 'text-text-primary'}`}>
        {value}
      </div>
      <div className="text-sm text-text-muted mt-1.5">{label}</div>
    </div>
  )
}

function SettingsMenu({ items }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-label="Profile settings"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="h-11 w-11 flex items-center justify-center rounded-lg border border-border bg-bg-raised text-text-primary hover:border-secondary transition-colors"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-48 z-30 rounded-lg border border-border bg-bg-surface shadow-xl py-1">
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                item.onClick()
              }}
              className="w-full text-left px-4 py-2.5 text-sm text-text-primary hover:bg-bg-raised"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * The profile's hero card: name, avatar ratings, postseason badge, the
 * headline ELO / rank / record, the period picker and the owner's actions.
 */
export default function PlayerHeader({
  data, playerId, headline = {}, avatarEntries = [], eventFilter, pastEvents, onEventChange,
  canSeeLifetime, onReport, settingsItems = [], onPostseason,
}) {
  const marks = useBracketMarks(playerId)
  const wins = data.wins ?? 0
  const losses = data.losses ?? 0

  return (
    <section
      aria-label="Player"
      className="rounded-2xl border border-border bg-bg-surface p-5 sm:p-7 flex flex-wrap gap-6 sm:gap-8 items-center"
    >
      <div className="flex items-center gap-5 flex-[1_1_380px] min-w-0">
        <ProfilePicture name={data.name} src={data.avatar_url} />
        <div className="min-w-0 flex flex-col gap-2">
          <h1 className="text-3xl sm:text-4xl font-display text-text-primary leading-tight break-words">
            <PostseasonName playerId={playerId} yurtSize={22}>
              <span tabIndex={0}>{data.name}</span>
            </PostseasonName>
          </h1>
          <div className="flex flex-wrap gap-2">
            {avatarEntries.length > 0 && (
              <ul className="contents" aria-label="Event ELO per avatar">
                {avatarEntries.map((entry) => (
                  <li
                    key={entry.avatar}
                    className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-bg-raised border border-border text-sm"
                  >
                    <strong className="text-text-primary">{entry.avatar}</strong>
                    <span className="text-text-muted tabular-nums">{entry.event_elo} · #{entry.rank}</span>
                  </li>
                ))}
              </ul>
            )}
            {marks?.best_label && (
              <button
                type="button"
                onClick={onPostseason}
                className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-bg-raised border border-secondary/40 text-sm hover:border-secondary"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" className="text-secondary" aria-hidden="true">
                  <path d="M2 19 L12 5 L22 19 Z" /><path d="M10 19 v-5 h4 v5" />
                </svg>
                <strong className="text-secondary">{marks.best_label}</strong>
                <span className="text-text-muted">Postseason</span>
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-8">
        {headline.elo != null && <BigStat value={headline.elo} label={headline.eloLabel} gold />}
        {headline.rank != null && <BigStat value={`#${headline.rank}`} label={headline.rankLabel} />}
        {wins + losses > 0 && (
          <BigStat value={`${data.win_rate ?? 0}%`} label={`${wins} W · ${losses} L`} />
        )}
        {headline.note && <p className="text-sm text-text-muted self-center">{headline.note}</p>}
      </div>

      <div className="flex flex-col gap-2.5">
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Period
          <select
            value={eventFilter}
            onChange={(e) => onEventChange(e.target.value)}
            className="h-11 min-w-[180px] rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary"
          >
            {canSeeLifetime && <option value="lifetime">Lifetime</option>}
            <option value="current">Current Event</option>
            {pastEvents.map((ev) => (
              <option key={ev.event_id} value={ev.event_id}>{ev.event_name}</option>
            ))}
          </select>
        </label>
        {onReport && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onReport}
              className="h-11 px-4 rounded-lg bg-secondary text-black text-sm font-semibold hover:opacity-90 transition-opacity"
            >
              Report a game
            </button>
            {settingsItems.length > 0 && <SettingsMenu items={settingsItems} />}
          </div>
        )}
      </div>
    </section>
  )
}
