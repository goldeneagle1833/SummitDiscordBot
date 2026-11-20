import { get, post, put, del } from './client'

// Admin > Events: run the Lavamancer vs Frostmage ladder without bot commands.
export const getPreconAdmin = () => get('/api/precon/admin')
export const updatePreconSettings = (changes) => put('/api/precon/admin/settings', changes)
export const startPreconSeason = (body) => post('/api/precon/admin/seasons', body)
export const updatePreconSeason = (seasonId, body) => put(`/api/precon/admin/seasons/${seasonId}`, body)
export const endPreconSeason = () => post('/api/precon/admin/seasons/end', {})
export const reportPreconMatch = (body) => post('/api/precon/admin/matches', body)
export const removePreconMatch = (matchId) => del(`/api/precon/admin/matches/${matchId}`)
