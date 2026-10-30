import { get, post } from './client'

// Paper tournament finishes: Top 8 page results matched to Summit profiles
export const getPaperFinishes = () => get('/api/paper-finishes')

// Admin review of how each result matched, and the admin's calls on it
export const getPaperFinishesReview = () => get('/api/admin/paper-finishes')
export const linkPaperName = (paperName, userId) =>
  post('/api/admin/paper-finishes/link', { paper_name: paperName, user_id: userId })
export const rejectPaperName = (paperName, userId) =>
  post('/api/admin/paper-finishes/link', { paper_name: paperName, user_id: userId, status: 'rejected' })
export const unlinkPaperName = (nameKey, userId) =>
  post('/api/admin/paper-finishes/unlink', { name_key: nameKey, user_id: userId })
export const assignPaperResult = (folder, deckId, userId) =>
  post('/api/admin/paper-finishes/assign', { folder, deck_id: deckId, user_id: userId || '' })
export const clearPaperResult = (folder, deckId) =>
  post('/api/admin/paper-finishes/assign', { folder, deck_id: deckId, clear: true })
export const setPaperEventBadges = (folder, awardsBadges) =>
  post('/api/admin/paper-finishes/event', { folder, awards_badges: awardsBadges })

// One event's Top 8 entries with the Summit profile each one matched
export const getEventProfiles = (folder) =>
  get(`/api/paper-finishes/event/${encodeURIComponent(folder)}`)
