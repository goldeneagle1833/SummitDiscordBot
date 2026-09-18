/**
 * Profile picture URL for a player.
 *
 * Discord gives us an avatar hash to build a CDN URL from; Google hands back a
 * URL already. Anyone without a stored avatar gets null, and the Avatar
 * component falls back to its placeholder.
 */
export function avatarUrl(player, size = 64) {
  if (!player?.avatar) return null
  if (player.provider === 'google') return player.avatar
  if (!player.user_id) return null
  return `https://cdn.discordapp.com/avatars/${player.user_id}/${player.avatar}.png?size=${size}`
}

/** Map of user_id -> avatar URL, for looking players up by id. */
export function avatarMap(players = [], size = 64) {
  const map = {}
  for (const player of players) {
    if (!player?.user_id) continue
    const url = avatarUrl(player, size)
    if (url) map[String(player.user_id)] = url
  }
  return map
}
