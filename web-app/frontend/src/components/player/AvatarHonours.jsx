import { useEffect, useState } from 'react'
import { getAvatarHonours } from '@/api/avatarHonours'

/**
 * Season avatar honours: the top three entries on each avatar's Elo ladder
 * (10+ games) in an Avatar-mode season, earned when the season is archived.
 * "Gothic Season 9 Top Imposter", "... 2nd Imposter", "... 3rd Imposter".
 *
 * Fetched once per page load and shared through a module-level cache, like
 * the bracket marks.
 */

export const PLACE_COLOURS = {
  1: 'text-secondary',
  2: 'text-slate-200',
  3: 'text-amber-600',
}

let cache = null
let inflight = null

function loadHonours() {
  if (cache) return Promise.resolve(cache)
  if (!inflight) {
    inflight = getAvatarHonours()
      .then((res) => {
        cache = res?.honours || {}
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

/** Test hook: drop the cached honours (and optionally preload known ones). */
export function resetAvatarHonoursCache(preload = null) {
  cache = preload
  inflight = null
}

/** One player's honours, newest season first ([] when they have none). */
export function useAvatarHonours(playerId) {
  const key = playerId == null ? '' : String(playerId)
  const [honours, setHonours] = useState(() => (cache && key ? cache[key] || [] : []))

  useEffect(() => {
    if (!key) {
      setHonours([])
      return undefined
    }
    let active = true
    loadHonours().then((all) => {
      if (active) setHonours(all[key] || [])
    })
    return () => {
      active = false
    }
  }, [key])

  return honours
}

function Medal({ place, size = 15 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      className={PLACE_COLOURS[place]}
      aria-hidden="true"
    >
      <path d="M8 2 L12 9 L16 2" />
      <circle cx="12" cy="15" r="6" />
      <text x="12" y="18" textAnchor="middle" fontSize="8" fill="currentColor" stroke="none" fontWeight="700">
        {place}
      </text>
    </svg>
  )
}

/**
 * The hero card chip: the player's best honour (highest place, newest
 * season), plus how many more they hold. Hovering lists them all.
 */
export function AvatarHonourBadge({ honours = [], onClick }) {
  if (!honours.length) return null
  const best = honours.reduce((a, b) => (b.place < a.place ? b : a))
  const more = honours.length - 1
  return (
    <button
      type="button"
      onClick={onClick}
      title={honours.map((h) => h.title).join('\n')}
      className="inline-flex flex-wrap items-center gap-x-2 px-3 py-1 rounded-2xl bg-bg-raised border border-secondary/40 text-sm hover:border-secondary text-left"
    >
      <Medal place={best.place} />
      <strong className={`whitespace-nowrap ${PLACE_COLOURS[best.place]}`}>{best.label}</strong>
      <span className="text-text-muted whitespace-nowrap">{best.season}</span>
      {more > 0 && <span className="text-text-muted">+{more}</span>}
    </button>
  )
}

/** The Postseason tab's list of honours, grouped by season. */
export function AvatarHonoursSection({ honours = [] }) {
  if (!honours.length) return null
  const seasons = []
  for (const honour of honours) {
    let group = seasons.find((s) => s.season === honour.season)
    if (!group) {
      group = { season: honour.season, honours: [] }
      seasons.push(group)
    }
    group.honours.push(honour)
  }

  return (
    <section className="space-y-4">
      <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted">Season avatar honours</h2>
      <ul className="space-y-3">
        {seasons.map((group) => (
          <li key={group.season} className="bg-bg-surface border border-border rounded-xl p-5">
            <div className="text-lg font-bold text-text-primary">{group.season}</div>
            <ul className="mt-3 flex flex-wrap gap-2">
              {group.honours.map((h) => (
                <li
                  key={`${h.avatar}-${h.place}`}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-bg-raised border border-border text-sm"
                >
                  <Medal place={h.place} />
                  <strong className={PLACE_COLOURS[h.place]}>{h.label}</strong>
                  <span className="text-text-muted tabular-nums">
                    {h.elo} Elo
                    {h.wins != null && ` · ${h.wins}-${h.losses}`}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <p className="text-xs text-text-muted">
        The top three on each avatar's season Elo ladder (Avatar-mode seasons, 10+ games, each player on their best avatar only), set when the season ends.
      </p>
    </section>
  )
}
