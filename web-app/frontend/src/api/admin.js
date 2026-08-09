import { get, post, put, del } from './client'

export const removePlayer = (userId) => del(`/api/admin/remove-player/${userId}`)

export const removeMatch = (matchId) => del(`/api/admin/remove-match/${matchId}`)

export const correctMatchAvatars = (matchId, winnerAvatar, loserAvatar) =>
  put(`/api/admin/correct-match-avatars/${matchId}`, {
    winner_avatar: winnerAvatar,
    loser_avatar: loserAvatar,
  })

export const resetElo = (userId, newElo, source, avatarName) =>
  post(`/api/admin/reset-elo/${userId}`, {
    new_elo: newElo,
    source,
    avatar_name: avatarName || undefined,
  })

export const renamePlayer = (userId, newName) =>
  post(`/api/admin/rename-player/${userId}`, { new_name: newName })

// Creator access management
export const getCreatorAccess = () => get('/api/admin/creator-access')

export const addCreatorAccess = (userId, displayName) =>
  post('/api/admin/creator-access', { user_id: userId, display_name: displayName })

export const removeCreatorAccess = (userId) =>
  del(`/api/admin/creator-access/${userId}`)

export const searchUsers = (q) =>
  get(`/api/admin/search-users?q=${encodeURIComponent(q)}`)

// Avatar image display settings
export const getAvatarImageSettings = () => get('/api/admin/avatar-image-settings')

export const updateAvatarImageSettings = (avatarName, settings) =>
  put(`/api/admin/avatar-image-settings/${encodeURIComponent(avatarName)}`, settings)

export const resetAvatarImageSettings = (avatarName) =>
  del(`/api/admin/avatar-image-settings/${encodeURIComponent(avatarName)}`)

export const deleteAccount = (userId) => del(`/api/admin/delete-account/${userId}`)

export const getMatchesWithNotes = (page = 1, perPage = 50) =>
  get(`/api/admin/matches-with-notes?page=${page}&per_page=${perPage}`)

// Reaction roles
export const getReactionRoleMessages = () => get('/api/reaction-roles/messages')
export const addReactionRoleMessage = (channelId, messageId, label) =>
  post('/api/reaction-roles/messages', { channel_id: channelId, message_id: messageId, label })
export const deleteReactionRoleMessage = (messageId) =>
  del(`/api/reaction-roles/messages/${messageId}`)
export const addReactionRoleMapping = (messageId, emoji, roleId, roleName, emojiId) =>
  post('/api/reaction-roles/mappings', { message_id: messageId, emoji, role_id: roleId, role_name: roleName, emoji_id: emojiId })
export const deleteReactionRoleMapping = (mappingId) =>
  del(`/api/reaction-roles/mappings/${mappingId}`)
