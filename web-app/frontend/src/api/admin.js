import { get, post, put, del } from './client'

export const removePlayer = (userId) => del(`/api/admin/remove-player/${userId}`)

export const removeMatch = (matchId) => del(`/api/admin/remove-match/${matchId}`)

export const resetElo = (userId, newElo, source) =>
  post(`/api/admin/reset-elo/${userId}`, { new_elo: newElo, source })

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

// User profiles (admin "add user by Discord name" page)
export const getUserProfiles = (q = '', limit = 50, offset = 0) =>
  get(`/api/admin/user-profiles?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`)

export const getUserProfileCandidates = (q) =>
  get(`/api/admin/user-profiles/candidates?q=${encodeURIComponent(q)}`)

export const addUserProfile = (userId, displayName, avatar) =>
  post('/api/admin/user-profiles', { user_id: userId, display_name: displayName, avatar })

export const deleteUserProfile = (userId) =>
  del(`/api/admin/user-profiles/${encodeURIComponent(userId)}`)

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

// Monitoring dashboard (requests, outbound services, resources, errors)
export const getMonitoring = (hours = 24) => get(`/api/admin/monitoring?hours=${hours}`)
