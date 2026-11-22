import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getProfileBadgePrefs } from '@/api/players'
import { FINISH_COLOURS as POSTSEASON_COLOURS, Yurt, useBracketMarks } from '@/components/player/BracketMarks'
import { Trophy, usePaperFinishes } from '@/components/player/PaperFinishes'
import { FoilAvatar, useEventAvatarBadges } from '@/components/player/EventAvatarBadges'
import { heroBadgeKeys, profileBadges } from '@/components/player/profileBadges'

/**
 * A player's achievements beside their name on the leaderboards: the same
 * event finishes their profile shows (their best 3, or the ones they
 * picked), as small icons. Season avatar honours show on the profile only.
 * Hover (or long-press) names each one; a tap opens the
 * player's Postseason tab. Postseason finishes are badges here too (the
 * leaderboards no longer colour names): a champion shows the yurt, other
 * finishes a trophy in that finish's colour.
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
  if (badge.kind === 'postseason') {
    if (badge.label === 'Champion') return <Yurt size={16} />
    return <Trophy size={14} className={POSTSEASON_COLOURS[badge.label] || 'text-text-muted'} />
  }
  if (badge.kind === 'event') return <FoilAvatar avatar={badge.avatar} size={20} id={`nb-${badge.key}`} />
  return <Trophy label={badge.label} size={14} />
}

export default function NameBadges({ playerId, className = '' }) {
  const marks = useBracketMarks(playerId)
  const paperFinishes = usePaperFinishes(playerId)
  const eventBadges = useEventAvatarBadges(playerId)
  const pref = useBadgePref(playerId)

  // Season avatar honours stay on the profile: the avatar leaderboard already
  // shows each avatar's current standing, so names here carry event finishes only.
  const all = profileBadges({ marks, paperFinishes, eventBadges })
  const keys = heroBadgeKeys(all, pref?.shown ?? null, pref?.hidden || [])
  const shown = all.filter((b) => keys.has(b.key))
  if (!shown.length) return null

  // Postseason hover lists every placement, as the coloured name used to.
  const placements = (marks?.entries || []).map((e) => `${e.label}: ${e.name}`).join('\n')
  const titleOf = (b) => {
    if (b.key === 'postseason' && placements) return `Postseason · ${b.label}\n${placements}`
    return b.title || `${b.label} · ${b.detail}`
  }

  return (
    <span className={`inline-flex items-center gap-1 align-middle ${className}`} aria-label="Achievements">
      {shown.map((b) => (
        <Link
          key={b.key}
          to={`/player/${playerId}?tab=postseason`}
          title={titleOf(b)}
          aria-label={titleOf(b)}
          className={b.kind === 'event'
            ? 'inline-flex items-center justify-center h-6 w-6 rounded-full hover:scale-110 transition-transform'
            : 'inline-flex items-center justify-center h-6 w-6 rounded-full bg-bg-raised border border-border hover:border-secondary transition-colors'}
        >
          <Icon badge={b} />
        </Link>
      ))}
    </span>
  )
}
