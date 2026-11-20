import { get } from './client'

// Every ladder, bracket and series, plus (logged in) where you stand in each.
export const getStandingsHub = () => get('/api/standings')
