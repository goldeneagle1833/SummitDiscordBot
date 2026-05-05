import { get, post, del } from './client'

export const fetchSeasons = () => get('/api/explorer/seasons')

export const createSeason = (name, description, pointsConfig) =>
  post('/api/explorer/seasons', { name, description, points_config: pointsConfig })

export const deleteSeason = (seasonId) =>
  del(`/api/explorer/seasons/${seasonId}`)

export const fetchSeasonEvents = (seasonId) =>
  get(`/api/explorer/seasons/${seasonId}/events`)

export const fetchLeaderboard = (seasonId) =>
  get(`/api/explorer/leaderboard/${seasonId}`)

export const previewEvent = (url, seasonId) =>
  post('/api/explorer/events/preview', { url, season_id: seasonId })

export const saveEvent = (url, seasonId) =>
  post('/api/explorer/events', { url, season_id: seasonId })

export const deleteEvent = (eventId) =>
  del(`/api/explorer/events/${eventId}`)

export const fetchAdmins = () => get('/api/explorer/admins')

export const addAdmin = (discordUserId, displayName) =>
  post('/api/explorer/admins', { discord_user_id: discordUserId, display_name: displayName })

export const removeAdmin = (discordUserId) =>
  del(`/api/explorer/admins/${discordUserId}`)
