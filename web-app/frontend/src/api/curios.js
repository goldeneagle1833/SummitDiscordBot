import { get } from './client'

export const getCurioEntries = () => get('/api/curios')
export const getCurioSets = () => get('/api/curios/sets')
