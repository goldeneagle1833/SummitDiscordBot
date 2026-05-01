import { get, post, put, del } from './client'

export const removePlayer = (userId) => del(`/api/admin/remove-player/${userId}`)

export const removeMatch = (matchId) => del(`/api/admin/remove-match/${matchId}`)

export const resetElo = (userId, newElo, source) =>
  post(`/api/admin/reset-elo/${userId}`, { new_elo: newElo, source })

export const renamePlayer = (userId, newName) =>
  post(`/api/admin/rename-player/${userId}`, { new_name: newName })

// Avatar image display settings
export const getAvatarImageSettings = () => get('/api/admin/avatar-image-settings')

export const updateAvatarImageSettings = (avatarName, settings) =>
  put(`/api/admin/avatar-image-settings/${encodeURIComponent(avatarName)}`, settings)

export const resetAvatarImageSettings = (avatarName) =>
  del(`/api/admin/avatar-image-settings/${encodeURIComponent(avatarName)}`)
