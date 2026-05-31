import { get, post } from './client'

export const getPlayer = (id, { event, source, page, perPage, casualPage } = {}) => {
  const params = new URLSearchParams()
  if (event && event !== 'lifetime') params.set('event', event)
  if (source) params.set('source', source)
  if (page) params.set('page', page)
  if (perPage) params.set('per_page', perPage)
  if (casualPage) params.set('casual_page', casualPage)
  const qs = params.toString()
  return get(`/api/player/${id}${qs ? '?' + qs : ''}`)
}

export const getPlayerAvatarStats = (id) => get(`/api/players/${id}/avatar-stats`)
export const setDisplayName = (id, name) => post(`/api/player/${id}/set-display-name`, { display_name: name })
export const searchPlayers = (query) => get(`/api/players/search?q=${encodeURIComponent(query)}`)
export const getProfileVisibility = (id) => get(`/api/player/${id}/visibility`)
export const setProfileVisibility = (id, sections) => post(`/api/player/${id}/visibility`, { sections })
