import { get } from './client'

export const getPlayer = (id) => get(`/api/players/${id}`)
export const getPlayerMatches = (id, page = 1) => get(`/api/players/${id}/matches?page=${page}`)
export const getPlayerAvatarStats = (id) => get(`/api/players/${id}/avatar-stats`)
