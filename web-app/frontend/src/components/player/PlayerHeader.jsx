import { useEffect, useRef, useState } from 'react'
import { DecayTag } from '@/components/common/DecayTag'
import PostseasonName, { useBracketMarks } from '@/components/player/BracketMarks'
import { AvatarHonourBadge, useAvatarHonours } from '@/components/player/AvatarHonours'
import { PaperFinishChips, usePaperFinishes } from '@/components/player/PaperFinishes'
import { EventAvatarBadgeChips, useEventAvatarBadges } from '@/components/player/EventAvatarBadges'
import { eventBadgeKey, heroBadgeKeys, paperBadgeKey, profileBadges } from '@/components/player/profileBadges'
import { ProvisionalTag } from '@/components/common/Provisional'
import { provisionalOf } from '@/utils/provisional'

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
 * A best postseason finish, constructed or Limited ("Limited Champion").
 * Hovering names the brackets it was earned in. Opens the Postseason tab.
 */
function PostseasonBadge({ label, entries = [], onClick }) {
  const where = entries.filter((e) => e.label === label).map((e) => e.name)
  return (
    <button
      type="button"
      onClick={onClick}
      title={where.length ? `${label}: ${where.join(', ')}` : undefined}
      className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-bg-raised border border-secondary/40 text-sm hover:border-secondary"
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" className="text-secondary" aria-hidden="true">
        <path d="M2 19 L12 5 L22 19 Z" /><path d="M10 19 v-5 h4 v5" />
      </svg>
      <strong className="text-secondary">{label}</strong>
      <span className="text-text-muted">Postseason</span>
    </button>
  )
}

/**
 * The profile's hero card: name, avatar ratings, postseason badge, the
 * headline ELO / rank / record, the period picker, the owner's actions and
 * the showcase row (featured deck, favorite card, home store) and bio.
 */
export default function PlayerHeader({
  data, playerId, headline = {}, avatarEntries = [], eventFilter, pastEvents, onEventChange,
  canSeeLifetime, onReport, settingsItems = [], onPostseason, featured = null, bio = null, hiddenBadges = [], shownBadges = null,
}) {
  const marks = useBracketMarks(playerId)
  const honours = useAvatarHonours(playerId)
  const allPaperFinishes = usePaperFinishes(playerId)
  const allEventBadges = useEventAvatarBadges(playerId)
  // The best 3 by default, or the player's own pick ("Profile badges");
  // the Postseason tab always lists every badge.
  const allBadges = profileBadges({
    marks, honours, paperFinishes: allPaperFinishes, eventBadges: allEventBadges,
  })
  const visible = heroBadgeKeys(allBadges, shownBadges, hiddenBadges)
  const shows = (key) => visible.has(key)
  const moreCount = allBadges.length - visible.size
  const moreButton = (
    <button
      type="button"
      onClick={onPostseason}
      className="inline-flex items-center px-3 py-1 rounded-full border border-border text-xs sm:text-sm text-text-muted hover:text-text-primary hover:border-secondary"
      title="See every badge in the Postseason tab"
    >
      +{moreCount} more
    </button>
  )
  const paperFinishes = allPaperFinishes.filter((f) => shows(paperBadgeKey(f)))
  const eventBadges = allEventBadges.filter((b) => shows(eventBadgeKey(b)))
  // The "+N more" button follows the last row of chips
  const chipRows = eventBadges.length > 0 || paperFinishes.length > 0
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
            {marks?.best_label && shows('postseason') && (
              <PostseasonBadge label={marks.best_label} entries={marks.entries} onClick={onPostseason} />
            )}
            {marks?.limited_best_label && shows('postseason_limited') && (
              <PostseasonBadge
                label={marks.limited_best_label}
                entries={marks.entries}
                onClick={onPostseason}
              />
            )}
            {marks?.underdog_best_label && shows('postseason_underdog') && (
              <PostseasonBadge
                label={marks.underdog_best_label}
                entries={marks.entries}
                onClick={onPostseason}
              />
            )}
            {shows('avatar_honours') && <AvatarHonourBadge honours={honours} onClick={onPostseason} />}
            {moreCount > 0 && !chipRows && moreButton}
          </div>
          {bio}
        </div>
      </div>

      {eventBadges.length > 0 && (
        <div className="basis-full -mt-2 lg:order-last">
          <EventAvatarBadgeChips badges={eventBadges} />
        </div>
      )}

      {paperFinishes.length > 0 && (
        <div className="basis-full -mt-2 lg:order-last">
          <PaperFinishChips finishes={paperFinishes} />
        </div>
      )}

      {moreCount > 0 && chipRows && (
        <div className="basis-full -mt-2 lg:order-last">{moreButton}</div>
      )}

      {avatarEntries.length > 0 && (
        <ul className="basis-full flex flex-wrap gap-2 -mt-2 lg:order-last" aria-label="Event Rating per avatar">
          {avatarEntries.map((entry) => (
            <li
              key={entry.avatar}
              className="inline-flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1 rounded-full bg-bg-raised border border-border text-xs sm:text-sm"
            >
              <strong className="text-text-primary">{entry.avatar}</strong>
              {provisionalOf(entry) ? (
                <ProvisionalTag games={provisionalOf(entry).games} />
              ) : (
                <span className="text-text-muted tabular-nums">
                  {entry.event_elo}{entry.rank != null && ` · #${entry.rank}`}
                </span>
              )}
              {!provisionalOf(entry) && <DecayTag decay={entry.decay} inDays={entry.decay_in_days} />}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-8">
        {headline.provisional ? (
          <div>
            <div className="h-10 flex items-end">
              <ProvisionalTag
                games={headline.provisional.games}
                className="px-2.5 py-1 rounded-full bg-bg-raised border border-border text-sm"
              />
            </div>
            <div className="text-sm text-text-muted mt-1.5">{headline.eloLabel}</div>
          </div>
        ) : (
          headline.elo != null && <BigStat value={headline.elo} label={headline.eloLabel} gold />
        )}
        {headline.legacyElo != null && <BigStat value={headline.legacyElo} label="Legacy Rating (Seasons 1-8)" />}
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

      {/* Featured deck, favorite card, home store: only the filled ones for
          visitors, so the row disappears when a player has none */}
      {featured && (
        <div className="basis-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 empty:hidden">
          {featured}
        </div>
      )}
    </section>
  )
}
