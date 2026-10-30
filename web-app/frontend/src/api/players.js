import { get, post, put, del } from './client'

export const getPlayer = (id, { event, source, page, perPage, casualPage, externalPage, filters = {} } = {}) => {
  const params = new URLSearchParams()
  if (event && event !== 'lifetime') params.set('event', event)
  if (source) params.set('source', source)
  if (page) params.set('page', page)
  if (perPage) params.set('per_page', perPage)
  if (casualPage) params.set('casual_page', casualPage)
  if (externalPage) params.set('external_page', externalPage)
  for (const key of ['opponent', 'result', 'avatar', 'opponent_avatar', 'play_draw']) {
    if (filters[key]) params.set(key, filters[key])
  }
  const qs = params.toString()
  return get(`/api/player/${id}${qs ? '?' + qs : ''}`)
}

export const getPlayerAvatarStats = (id, avatarName, { event } = {}) => {
  const params = new URLSearchParams()
  if (event && event !== 'lifetime') params.set('event', event)
  const qs = params.toString()
  return get(`/api/player/${id}/avatar/${encodeURIComponent(avatarName)}${qs ? '?' + qs : ''}`)
}
export const setDisplayName = (id, name) => post(`/api/player/${id}/set-display-name`, { display_name: name })
export const searchPlayers = (query) => get(`/api/players/search?q=${encodeURIComponent(query)}`)
export const getProfileVisibility = (id) => get(`/api/player/${id}/visibility`)
export const setProfileVisibility = (id, sections) => post(`/api/player/${id}/visibility`, { sections })
export const resetOwnProfile = (id) => post(`/api/player/${id}/reset-profile`)
export const undoProfileReset = (id) => post(`/api/player/${id}/undo-reset`)
export const deleteOwnAccount = (id) => del(`/api/player/${id}/account`)
export const getBlockedUsers = (id) => get(`/api/player/${id}/blocked-users`)
export const blockUser = (id, blockedUserId, reason) => post(`/api/player/${id}/blocked-users`, { blocked_user_id: blockedUserId, reason })
export const unblockUser = (id, blockedUserId) => del(`/api/player/${id}/blocked-users/${blockedUserId}`)
export const getQueueSettings = (id) => get(`/api/player/${id}/queue-settings`)
export const setQueueSettings = (id, settings) => post(`/api/player/${id}/queue-settings`, settings)
export const getPlayerCardStats = (id, { event, queue } = {}) => {
  const params = new URLSearchParams()
  if (event && event !== 'lifetime') params.set('event', event)
  if (queue && queue !== 'all') params.set('queue', queue)
  const qs = params.toString()
  return get(`/api/player/${id}/card-stats${qs ? '?' + qs : ''}`)
}

/** Hide avatars from the player's own profile. Their games are kept. */
export const setHiddenAvatars = (id, avatars) => put(`/api/player/${id}/hidden-avatars`, { avatars })

/** The deck a player features on their profile: { deck, mode } (deck is null when none). */
export const getFeaturedDeck = (id) => get(`/api/player/${id}/featured-deck`)
export const setFeaturedDeck = (id, url, autoUpdate) =>
  put(`/api/player/${id}/featured-deck`, { url, auto_update: autoUpdate })
/** Go back to featuring the player's most-played public deck. */
export const setFeaturedDeckAuto = (id) => put(`/api/player/${id}/featured-deck`, { mode: 'auto' })
/** Show no featured deck at all. */
export const clearFeaturedDeck = (id) => del(`/api/player/${id}/featured-deck`)
