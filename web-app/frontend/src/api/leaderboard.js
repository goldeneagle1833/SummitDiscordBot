import { get } from './client'

export const getLeaderboard = () => get('/api/leaderboard')
export const getEventLeaderboard = () => get('/api/leaderboard/event')
// The running season's ladder split per avatar (Avatar-mode seasons), in plain Elo order
export const getAvatarLeaderboards = () => get('/api/leaderboard/avatars?min_games=0')
// Lifetime avatar ELO per avatar (Glicko-2, Season 9 on; empty before), same shape
export const getLifetimeAvatarLeaderboards = () => get('/api/leaderboard/avatars?min_games=0&scope=lifetime')
export const getPaperEventLeaderboard = () => get('/api/leaderboard/paper-event')
export const getLimitedLeaderboard = (view = 'lifetime') => get(`/api/leaderboard/limited?view=${view}`)
export const getArchivedLimitedEvents = () => get('/api/leaderboard/limited/archived')
export const getArchivedLimitedLeaderboard = (eventId) => get(`/api/leaderboard/limited/archived/${eventId}`)
export const getRunMatchups = (runId) => get(`/api/limited/run/${runId}/matchups`)
// Lavamancer vs Frostmage precon ladder (current or latest season unless one is named)
export const getPreconStandings = (seasonId) => get(seasonId ? `/api/precon/standings?season_id=${seasonId}` : '/api/precon/standings')
export const getCombinedLeaderboard = () => get('/api/leaderboard/combined')
export const getEloDistribution = () => get('/api/elo-distribution')
export const getEvents = () => get('/api/events')
export const getArchivedLeaderboard = (eventId) =>
  get(String(eventId).startsWith('season_')
    ? `/api/leaderboard/archived/season/${eventId}`
    : `/api/leaderboard/archived/${eventId}`)
// One player's LM / FM ladder standings and latest precon games
export const getPreconPlayer = (playerId) => get(`/api/precon/players/${playerId}`)
