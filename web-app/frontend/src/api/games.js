import { get, post, put } from './client'

export const recordGame = (body) => post('/api/record-game', body)

export const submitMatchReport = (body) => post('/api/match-report/submit', body)

export const searchOpponents = (query, limit = 10) =>
  get(`/api/match-report/search-opponents?q=${encodeURIComponent(query)}&limit=${limit}`)

export const listAllAvatars = () => get('/api/list-all-avatars')

export const updateMatchDeck = (matchId, deckUrl, source) =>
  put('/api/update-match-deck', { match_id: matchId, deck_url: deckUrl, source })

export const editMatchComment = (matchId, matchSource, newComment) =>
  post('/api/match-report/edit-comment', { match_id: matchId, match_source: matchSource, new_comment: newComment })

export const editMatchTime = (matchId, matchSource, matchTime) =>
  post('/api/match-report/edit-match-time', { match_id: matchId, match_source: matchSource, match_time: matchTime })
