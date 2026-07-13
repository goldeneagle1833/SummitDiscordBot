import { get, post, del } from './client'

export const getPlayer = (id, { event, source, page, perPage, casualPage, externalPage } = {}) => {
  const params = new URLSearchParams()
  if (event && event !== 'lifetime') params.set('event', event)
  if (source) params.set('source', source)
  if (page) params.set('page', page)
  if (perPage) params.set('per_page', perPage)
  if (casualPage) params.set('casual_page', casualPage)
  if (externalPage) params.set('external_page', externalPage)
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
export const deleteOwnAccount = (id) => del(`/api/player/${id}/account`)
export const getBlockedUsers = (id) => get(`/api/player/${id}/blocked-users`)
export const blockUser = (id, blockedUserId) => post(`/api/player/${id}/blocked-users`, { blocked_user_id: blockedUserId })
export const unblockUser = (id, blockedUserId) => del(`/api/player/${id}/blocked-users/${blockedUserId}`)
