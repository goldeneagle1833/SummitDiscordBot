/**
 * Helpers for the "top player with this avatar" badges on the home leaderboard.
 */

/** Match an avatar name (e.g. "Avatar of Earth") to a file in /avatar-images. */
export function getAvatarImagePath(name, files = []) {
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
  const n = norm(name)
  const stems = files.map((f) => [f, norm(f.replace(/\.\w+$/, ''))])
  return (
    stems.find(([, s]) => s === n)?.[0] ??
    stems.find(([, s]) => s.includes(n))?.[0] ??
    stems.find(([, s]) => n.includes(s))?.[0] ??
    null
  )
}

/**
 * Group badges by player id: { [playerId]: [{ avatar, imgSrc, wins, losses, avatar_score }] }.
 * A player who tops several avatars gets several badges, best score first.
 */
export function badgesByPlayer(badges = [], imageFiles = []) {
  const map = {}
  for (const b of badges) {
    if (!b?.player_id || !b.avatar) continue
    const file = getAvatarImagePath(b.avatar, imageFiles)
    const entry = { ...b, imgSrc: file ? `/avatar-images/${file}` : null }
    ;(map[String(b.player_id)] ||= []).push(entry)
  }
  for (const list of Object.values(map)) {
    list.sort((a, b) => (b.avatar_score ?? 0) - (a.avatar_score ?? 0))
  }
  return map
}
