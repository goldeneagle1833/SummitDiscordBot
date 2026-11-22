import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getEventAvatarBadges } from '@/api/paperFinishes'
import { getAvatarImageFiles } from '@/api/cards'
import { getAvatarImagePath } from '@/utils/avatarBadges'

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

/**
 * A small rainbow foil card: the event's prize for topping an avatar is a
 * rainbow foil card of that avatar, so the badge looks like one.
 */
export function FoilCard({ size = 16, id = 'foil' }) {
  const grad = `foil-${String(id).replace(/[^A-Za-z0-9_-]/g, '_')}`
  return (
    <svg width={size * 0.75} height={size} viewBox="0 0 18 24" aria-hidden="true" className="shrink-0">
      <defs>
        <linearGradient id={grad} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff5f6d" />
          <stop offset="0.2" stopColor="#ffc371" />
          <stop offset="0.4" stopColor="#f9f871" />
          <stop offset="0.6" stopColor="#6dfba5" />
          <stop offset="0.8" stopColor="#47c5ff" />
          <stop offset="1" stopColor="#a77bff" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="16" height="22" rx="2.5" fill={`url(#${grad})`} />
      <rect x="3" y="3" width="12" height="18" rx="1.5" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="1" />
      <path d="M9 7 L10.2 10.8 L14 12 L10.2 13.2 L9 17 L7.8 13.2 L4 12 L7.8 10.8 Z" fill="white" opacity="0.9" />
    </svg>
  )
}

let filesCache = null
let filesInflight = null

function loadAvatarFiles() {
  if (filesCache) return Promise.resolve(filesCache)
  if (!filesInflight) {
    filesInflight = getAvatarImageFiles()
      .then((res) => {
        filesCache = Array.isArray(res) ? res : res?.files || []
        return filesCache
      })
      .catch(() => {
        filesCache = []
        return filesCache
      })
      .finally(() => {
        filesInflight = null
      })
  }
  return filesInflight
}

/** Test hook: preload the avatar image file list. */
export function resetAvatarFilesCache(preload = null) {
  filesCache = preload
  filesInflight = null
}

/** The avatar's stored portrait path, or null when none is on file. */
export function useAvatarImage(avatar) {
  const pick = (files) => {
    const file = files && avatar ? getAvatarImagePath(avatar, files) : null
    return file ? `/avatar-images/${file}` : null
  }
  const [src, setSrc] = useState(() => pick(filesCache))
  useEffect(() => {
    let active = true
    loadAvatarFiles().then((files) => {
      if (active) setSrc(pick(files))
    })
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatar])
  return src
}

/**
 * The avatar's portrait in a rainbow foil ring: the badge looks like the
 * event's prize, a rainbow foil card of that avatar. Falls back to the foil
 * card icon when the avatar has no picture on file.
 */
export function FoilAvatar({ avatar, size = 22, id = 'fa' }) {
  const src = useAvatarImage(avatar)
  if (!src) return <FoilCard size={size} id={id} />
  return (
    <span className="foil-ring" aria-hidden="true">
      <img
        src={src}
        alt=""
        width={size}
        height={size}
        loading="lazy"
        style={{ width: size, height: size }}
        className="object-cover object-top"
      />
    </span>
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
            className="foil-chip flex items-center gap-1.5 sm:gap-2 max-w-full px-2.5 sm:px-3 py-1 rounded-full text-xs sm:text-sm"
          >
            <FoilAvatar avatar={b.avatar} size={20} id={`chip-${b.avatar}`} />
            <strong className="foil-text whitespace-nowrap">{b.label}</strong>
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
            <span className="foil-chip inline-flex items-center gap-2 px-2.5 py-1 rounded-full">
              <FoilAvatar avatar={b.avatar} size={26} id={`row-${b.folder}-${b.avatar}`} />
              <strong className="foil-text">{b.label}</strong>
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
        The best finish on each avatar across an event's whole field, awarded by an admin from the event's Top 8 page. Rainbow foil, like the event's prize: a rainbow foil card of that avatar.
      </p>
    </section>
  )
}
