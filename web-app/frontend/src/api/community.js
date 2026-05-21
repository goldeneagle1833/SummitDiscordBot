import { get, post, del } from './client'

export const getCommunity = () => get('/api/community')
export const addCommunityEntry = (data) => post('/api/community', data)
export const deleteCommunityEntry = (type, id) => del(`/api/community/${type}/${id}`)
