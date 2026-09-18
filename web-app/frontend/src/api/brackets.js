import { get, post, put, patch, del } from './client'

// Public
export const listBrackets = () => get('/api/brackets')
export const getBracket = (slug) => get(`/api/brackets/${slug}`)

// Logged-in players
export const getMyBracketMatches = () => get('/api/brackets/my-matches')
export const reportBracketMatch = (slug, matchNo, winnerUserId) =>
  post(`/api/brackets/${slug}/matches/${matchNo}/report`, { winner_user_id: winnerUserId })
export const confirmBracketMatch = (slug, matchNo, agree) =>
  post(`/api/brackets/${slug}/matches/${matchNo}/confirm`, { agree })

// Admin
export const adminListBrackets = () => get('/api/admin/brackets')
export const adminGetBracket = (slug) => get(`/api/admin/brackets/${slug}`)
export const adminPreviewBracket = (slug) => get(`/api/admin/brackets/${slug}/preview`)
export const adminGetSeedPool = (source) =>
  get(`/api/admin/brackets/seed-pool?source=${encodeURIComponent(source)}`)
export const adminSyncTickets = () => post('/api/admin/brackets/sync-tickets', {})
export const adminCreateBracket = (body) => post('/api/admin/brackets', body)
export const adminUpdateBracket = (slug, body) => patch(`/api/admin/brackets/${slug}`, body)
export const adminSetEntrants = (slug, entrants) =>
  put(`/api/admin/brackets/${slug}/entrants`, { entrants })
export const adminShuffleSeeds = (slug) => post(`/api/admin/brackets/${slug}/shuffle`, {})
export const adminMoveEntrant = (slug, seed, toSeed) =>
  post(`/api/admin/brackets/${slug}/move`, { seed, to_seed: toSeed })
export const adminPublishBracket = (slug) => post(`/api/admin/brackets/${slug}/publish`, {})
export const adminUnpublishBracket = (slug) => post(`/api/admin/brackets/${slug}/unpublish`, {})
export const adminSetMatchResult = (slug, matchNo, winnerUserId) =>
  post(`/api/admin/brackets/${slug}/matches/${matchNo}/result`, { winner_user_id: winnerUserId })
export const adminResetMatch = (slug, matchNo) =>
  post(`/api/admin/brackets/${slug}/matches/${matchNo}/reset`, {})
export const adminDeleteBracket = (slug) => del(`/api/admin/brackets/${slug}`)
