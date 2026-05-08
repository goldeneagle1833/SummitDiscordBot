import { get, post } from './client'

export const getCommunity = () => get('/api/community')
export const addCommunityEntry = (data) => post('/api/community', data)
