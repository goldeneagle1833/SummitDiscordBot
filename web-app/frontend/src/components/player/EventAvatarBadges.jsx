import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getEventAvatarBadges } from '@/api/paperFinishes'

/**
 * Event avatar badges: an admin awards them from an event's Top 8 page. The
 * best finisher on each avatar in that event's whole field earns
 * "Top Sparkmage · Avatar of the Realm 2026".
 *
 * Fetched once per page load and shared through a module-level cache, like
 * the paper finishes.
 */

let cache = null
let inflight = null

function loadBadges() {
  if (cache) return Promise.resolve(cache)
  if (!inflight) {
    inflight = getEventAvatarBadges()
      .then((res) => {
        cache = res?.badges || {}
        return cache
      })
      .catch(() => {
        // A profile should never fail over its decorations.
        cache = {}
        return cache
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

/** Drop the cached badges (after an award), or preload known ones in tests. */
export function resetEventAvatarBadgesCache(preload = null) {
  cache = preload
  inflight = null
}

const bareId = (id) => (id.startsWith('google_') ? id.slice(7) : id)

/** One player's event avatar badges, newest event first ([] when none). */
export function useEventAvatarBadges(playerId) {
  const key = playerId == null ? '' : bareId(String(playerId))
  const [badges, setBadges] = useState(() => (cache && key ? cache[key] || [] : []))

  useEffect(() => {
    if (!key) {
      setBadges([])
      return undefined
    }
    let active = true
    loadBadges().then((all) => {
      if (active) setBadges(all[key] || [])
    })
    return () => {
      active = false
    }
  }, [key])

  return badges
}

export function Crown({ size = 15, className = 'text-secondary' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M3 18 L5 7 L10 12 L12 5 L14 12 L19 7 L21 18 Z" />
      <path d="M3 21 h18" />
    </svg>
  )
}

const eventPath = (folder) => `/top-8/${encodeURIComponent(folder)}`

/** Hero card chips: one per badge, each opening its event's Top 8 page. */
export function EventAvatarBadgeChips({ badges = [] }) {
  if (!badges.length) return null
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Event avatar badges">
      {badges.map((b) => (
        <li key={`${b.folder}-${b.avatar}`} className="min-w-0 max-w-full">
          <Link
            to={eventPath(b.folder)}
            title={b.title}
            className="flex items-center gap-1.5 sm:gap-2 max-w-full px-2.5 sm:px-3 py-1 rounded-full bg-bg-raised border border-secondary/40 text-xs sm:text-sm hover:border-secondary"
          >
            <Crown size={14} />
            <strong className="whitespace-nowrap text-secondary">{b.label}</strong>
            <span className="text-text-muted truncate">{b.event}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function record(b) {
  if (b.wins == null) return null
  return `${b.wins}-${b.losses}${b.draws ? `-${b.draws}` : ''}`
}

/** The Postseason tab's list of event avatar badges, newest event first. */
export function EventAvatarBadgesSection({ badges = [] }) {
  if (!badges.length) return null
  return (
    <section className="space-y-4">
      <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Top avatar at an event</h2>
      <ul className="bg-bg-surface border border-border rounded-xl divide-y divide-border">
        {badges.map((b) => (
          <li key={`${b.folder}-${b.avatar}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3">
            <span className="inline-flex items-center gap-2 min-w-[9rem]">
              <Crown />
              <strong className="text-secondary">{b.label}</strong>
            </span>
            <Link to={eventPath(b.folder)} className="font-semibold text-text-primary hover:text-secondary flex-1 min-w-[12rem]">
              {b.event}
            </Link>
            <span className="text-sm text-text-muted">
              {[
                b.finish,
                record(b),
                b.avatar_players > 1 && `best of ${b.avatar_players} ${b.avatar} players`,
                b.event_date_display,
              ].filter(Boolean).join(' · ')}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-text-muted">
        The best finish on each avatar across an event's whole field, awarded by an admin from the event's Top 8 page.
      </p>
    </section>
  )
}
