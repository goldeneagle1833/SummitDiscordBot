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

// Venue attendance
export const fetchVenueAttendance = (url) =>
  post('/api/explorer/venue-attendance', { url })

// Player merge / aliases
export const fetchAllPlayers = () => get('/api/explorer/players')

export const fetchPotentialDuplicates = () => get('/api/explorer/players/duplicates')

export const fetchAliases = () => get('/api/explorer/players/aliases')

export const mergePlayers = (aliasUserId, canonicalUserId, aliasDisplayName, canonicalDisplayName) =>
  post('/api/explorer/players/merge', {
    alias_user_id: aliasUserId,
    canonical_user_id: canonicalUserId,
    alias_display_name: aliasDisplayName,
    canonical_display_name: canonicalDisplayName,
  })

export const deleteAlias = (aliasId) =>
  del(`/api/explorer/players/aliases/${aliasId}`)

// Events map + public settings
export const fetchExplorerSettings = () => get('/api/explorer/settings')

export const updateExplorerSettings = (eventsMapEnabled) =>
  post('/api/explorer/settings', { events_map_enabled: eventsMapEnabled })

export const fetchEventsMap = (seasonId) =>
  get(`/api/explorer/events-map${seasonId ? `?season_id=${seasonId}` : ''}`)

export const fetchUnmappedEvents = () => get('/api/explorer/events/unmapped')

export const geocodeEvent = (eventId) =>
  post(`/api/explorer/events/${eventId}/geocode`)

// Plain links so the browser downloads the file with the session cookie.
export const leaderboardExportUrl = (seasonId, view = 'standings') =>
  `/api/explorer/leaderboard/${seasonId}/export.csv?view=${view}`

// The Explorer Series site's editable text (hero, links, sections)
export const fetchSiteContent = () => get('/api/explorer/site-content')
export const saveSiteContent = (content) => post('/api/explorer/site-content', content)

// Uploads pictures for the Explorer Series site; resolves to { urls }.
export const uploadSiteImages = (files) => {
  const fd = new FormData()
  for (const file of files) fd.append('image', file)
  return fetch('/api/explorer/upload-image', { method: 'POST', body: fd, credentials: 'include' })
    .then(async (res) => {
      const d = await res.json().catch(() => ({}))
      if (res.status === 413) throw new Error('Those pictures are too big to send together. Try fewer at a time.')
      if (!res.ok || !d.success) throw new Error(d.error || res.statusText)
      return d
    })
}
