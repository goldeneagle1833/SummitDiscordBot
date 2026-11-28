import { get, post, put, del, getBlob, ApiError } from './client'
import { ensureSiteSession, refreshSiteSession, isGateRejection } from './siteSession'

export const getPlayer = (id, { event, source, page, perPage, casualPage, externalPage, filters = {} } = {}) => {
  const params = new URLSearchParams()
  if (event && event !== 'lifetime') params.set('event', event)
  if (source) params.set('source', source)
  if (page) params.set('page', page)
  if (perPage) params.set('per_page', perPage)
  if (casualPage) params.set('casual_page', casualPage)
  if (externalPage) params.set('external_page', externalPage)
  // One Match History list with ranked and casual games together
  params.set('combined', '1')
  for (const key of ['opponent', 'result', 'avatar', 'opponent_avatar', 'play_draw', 'card', 'game_type']) {
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
export const downloadOwnData = (id) => getBlob(`/api/player/${id}/data-export`)
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
export const setHiddenBadges = (id, hidden) => put(`/api/player/${id}/hidden-badges`, { hidden })
/** The hero card badges a player picked, in order; null = their best 3 (the default). */
export const setShownBadges = (id, shown) => put(`/api/player/${id}/shown-badges`, { shown })

/** The deck a player chose to feature on their profile: { deck } (null when none). */
export const getFeaturedDeck = (id) => get(`/api/player/${id}/featured-deck`)
export const setFeaturedDeck = (id, url, autoUpdate) =>
  put(`/api/player/${id}/featured-deck`, { url, auto_update: autoUpdate })
export const clearFeaturedDeck = (id) => del(`/api/player/${id}/featured-deck`)

/** The player's own profile boxes: { bio, favorite_card, rival } (each null when not set). */
export const getShowcase = (id) => get(`/api/player/${id}/showcase`)
/** Change any of bio / favorite_card (a card name) / rival (a player id); empty clears. */
export const setShowcase = (id, fields) => put(`/api/player/${id}/showcase`, fields)
/** The player's picture: { kind: 'discord' | 'card' | 'upload', card, url, discord_url }. Owner or staff. */
export const getProfilePicture = (id) => get(`/api/player/${id}/profile-picture`)
/** { kind: 'discord' } goes back to the Discord picture; { kind: 'card', card: name } uses card art. */
export const setProfilePicture = (id, choice) => put(`/api/player/${id}/profile-picture`, choice)
/** Image URL of the round picture a card would make (nothing is saved). */
export const cardPicturePreviewUrl = (id, card) =>
  `${import.meta.env.VITE_API_BASE_URL || ''}/api/player/${id}/profile-picture/card-preview?card=${encodeURIComponent(card)}`
/** Upload a picture; crop is { x, y, size } in fractions of the image (see the picker). */
export async function uploadProfilePicture(id, file, crop) {
  const form = () => {
    const fd = new FormData()
    fd.append('image', file, file.name || 'picture.jpg')
    if (crop) {
      fd.append('crop_x', String(crop.x))
      fd.append('crop_y', String(crop.y))
      fd.append('crop_size', String(crop.size))
    }
    return fd
  }
  const url = `${import.meta.env.VITE_API_BASE_URL || ''}/api/player/${id}/profile-picture/upload`
  const send = () => fetch(url, { method: 'POST', credentials: 'include', body: form() })
  await ensureSiteSession().catch(() => {})
  let res = await send()
  let data = await res.json().catch(() => ({}))
  if (!res.ok && isGateRejection(res, data)) {
    await refreshSiteSession().catch(() => {})
    res = await send()
    data = await res.json().catch(() => ({}))
  }
  if (res.status === 413) throw new ApiError(413, 'That picture is too big. Try a smaller one.')
  if (!res.ok) throw new ApiError(res.status, data.error || res.statusText)
  return data
}
/** Players this player has played, most games first: { players: [{ id, name, wins, losses }] }. */
export const getRivalOptions = (id) => get(`/api/player/${id}/rival-options`)

/** Which badges each player chose to show by their name ({ prefs: { id: { shown, hidden } } }). */
export const getProfileBadgePrefs = () => get('/api/profile-badge-prefs')
