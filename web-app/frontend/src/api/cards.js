import { get } from './client'

export const getAvatars = (params) => {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  return get(`/api/avatars${query}`)
}
export const getAvatarTopPlayers = (params) => {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  return get(`/api/avatars/top-players${query}`)
}
export const getAvatar = (name) => get(`/api/avatars/${encodeURIComponent(name)}`)
export const getAvatarImageFiles = () => get('/api/avatars/image-files')
export const getAvatarFilters = () => get('/api/avatars/filters')
export const getPlayDrawStats = () => get('/api/avatars/play-draw-stats')
export const getCards = (params) => {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  return get(`/api/cards${query}`)
}
export const getCard = (name) => get(`/api/card/${encodeURIComponent(name)}`)
