import { get } from './client'

export const getMatches = (date) => get(date ? `/api/match-history?date=${date}` : '/api/match-history')
export const getAvailableDates = () => get('/api/match-history/available-dates')
