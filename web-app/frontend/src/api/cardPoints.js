import { get, post, del } from './client'

export const fetchCardPointsAdmins = () => get('/api/card-points/admins')

export const addCardPointsAdmin = (discordUserId, displayName) =>
  post('/api/card-points/admins', { discord_user_id: discordUserId, display_name: displayName })

export const removeCardPointsAdmin = (discordUserId) =>
  del(`/api/card-points/admins/${discordUserId}`)
