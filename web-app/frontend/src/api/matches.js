import { get } from './client'

export const getMatches = (date) => get(date ? `/api/match-history?date=${date}` : '/api/match-history')
export const getAvailableDates = () => get('/api/match-history/available-dates')
export const getRecap = (kind, date) => get(`/api/match-history/recap?kind=${encodeURIComponent(kind)}&date=${encodeURIComponent(date)}`)
