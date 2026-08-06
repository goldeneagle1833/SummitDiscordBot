import { get, post, put, del } from './client'

export const recordGame = (body) => post('/api/record-game', body)

export const submitMatchReport = (body) => post('/api/match-report/submit', body)

export const searchOpponents = (query, limit = 10) =>
  get(`/api/match-report/search-opponents?q=${encodeURIComponent(query)}&limit=${limit}`)

export const listAllAvatars = () => get('/api/list-all-avatars')

export const updateMatchDeck = (matchId, deckUrl, source) =>
  put('/api/update-match-deck', { match_id: matchId, deck_url: deckUrl, source })

export const editMatchComment = (matchId, matchSource, newComment) =>
  post('/api/match-report/edit-comment', { match_id: matchId, match_source: matchSource, new_comment: newComment })

export const getPlayerSeasons = (playerId) => get(`/api/player/${playerId}/seasons`)

// Season management
export const createSeason = (body) => post('/api/seasons', body)
export const searchSeasons = (q) =>
  get(q ? `/api/seasons/search?q=${encodeURIComponent(q)}` : '/api/seasons/search')
export const joinSeason = (seasonId) => post(`/api/seasons/${seasonId}/join`)
export const leaveSeason = (seasonId) => post(`/api/seasons/${seasonId}/leave`)
export const modifySeason = (seasonId, body) => put(`/api/seasons/${seasonId}`, body)
export const endSeason = (seasonId) => post(`/api/seasons/${seasonId}/end`)
export const deleteSeason = (seasonId) => del(`/api/seasons/${seasonId}`)
export const kickSeasonMember = (seasonId, userId) =>
  post(`/api/seasons/${seasonId}/kick`, { user_id: userId })
export const reportSeasonMatch = (seasonId, winnerId, loserId) =>
  post(`/api/seasons/${seasonId}/report-match`, { winner_id: winnerId, loser_id: loserId })
export const getSeasonMembers = (seasonId) => get(`/api/seasons/${seasonId}/members`)
