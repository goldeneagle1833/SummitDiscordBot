import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getProfileBadgePrefs } from '@/api/players'
import { useBracketMarks } from '@/components/player/BracketMarks'
import { Medal, useAvatarHonours } from '@/components/player/AvatarHonours'
import { Trophy, usePaperFinishes } from '@/components/player/PaperFinishes'
import { FoilCard, useEventAvatarBadges } from '@/components/player/EventAvatarBadges'
import { heroBadgeKeys, profileBadges } from '@/components/player/profileBadges'

/**
 * A player's achievements beside their name on the leaderboards: the same
 * badges their profile shows (their best 3, or the ones they picked), as
 * small icons. Hover (or long-press) names each one; a tap opens the
 * player's Postseason tab. Postseason finishes are left out here because the
 * name already shows them (coloured name and tent mark).
 */

let prefsCache = null
let prefsInflight = null

function loadPrefs() {
  if (prefsCache) return Promise.resolve(prefsCache)
  if (!prefsInflight) {
    prefsInflight = getProfileBadgePrefs()
      .then((res) => {
        prefsCache = res?.prefs || {}
        return prefsCache
      })
      .catch(() => {
        prefsCache = {}
        return prefsCache
      })
      .finally(() => {
        prefsInflight = null
      })
  }
  return prefsInflight
}

/** Test hook: drop the cached choices (and optionally preload known ones). */
export function resetBadgePrefsCache(preload = null) {
  prefsCache = preload
  prefsInflight = null
}

const bareId = (id) => (String(id).startsWith('google_') ? String(id).slice(7) : String(id))

function useBadgePref(playerId) {
  const key = playerId == null ? '' : bareId(playerId)
  const [pref, setPref] = useState(() => (prefsCache && key ? prefsCache[key] || null : null))
  useEffect(() => {
    if (!key) return undefined
    let active = true
    loadPrefs().then((all) => {
      if (active) setPref(all[key] || null)
    })
    return () => {
      active = false
    }
  }, [key])
  return pref
}

function Icon({ badge }) {
  if (badge.kind === 'event') return <FoilCard size={16} id={`nb-${badge.key}`} />
  if (badge.kind === 'honour') return <Medal place={badge.place} size={15} />
  return <Trophy label={badge.label} size={14} />
}

export default function NameBadges({ playerId, className = '' }) {
  const marks = useBracketMarks(playerId)
  const honours = useAvatarHonours(playerId)
  const paperFinishes = usePaperFinishes(playerId)
  const eventBadges = useEventAvatarBadges(playerId)
  const pref = useBadgePref(playerId)

  const all = profileBadges({ marks, honours, paperFinishes, eventBadges })
  const keys = heroBadgeKeys(all, pref?.shown ?? null, pref?.hidden || [])
  const shown = all.filter((b) => keys.has(b.key) && b.kind !== 'postseason')
  if (!shown.length) return null

  return (
    <span className={`inline-flex items-center gap-1 align-middle ${className}`} aria-label="Achievements">
      {shown.map((b) => (
        <Link
          key={b.key}
          to={`/player/${playerId}?tab=postseason`}
          title={b.title || `${b.label} · ${b.detail}`}
          aria-label={b.title || `${b.label} · ${b.detail}`}
          className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-bg-raised border border-border hover:border-secondary transition-colors"
        >
          <Icon badge={b} />
        </Link>
      ))}
    </span>
  )
}
