import { get } from './client'

export const getLeaderboard = () => get('/api/leaderboard')
export const getEventLeaderboard = () => get('/api/leaderboard/event')
export const getPaperEventLeaderboard = () => get('/api/leaderboard/paper-event')
export const getLimitedLeaderboard = () => get('/api/leaderboard/limited')
export const getRunMatchups = (runId) => get(`/api/limited/run/${runId}/matchups`)
export const getCombinedLeaderboard = () => get('/api/leaderboard/combined')
export const getEloDistribution = () => get('/api/elo-distribution')
export const getEvents = () => get('/api/events')
export const getArchivedLeaderboard = (eventId) =>
  get(String(eventId).startsWith('season_')
    ? `/api/leaderboard/archived/season/${eventId}`
    : `/api/leaderboard/archived/${eventId}`)
export const browseSeasons = (q) =>
  get(q ? `/api/seasons/browse?q=${encodeURIComponent(q)}` : '/api/seasons/browse')
