import { get } from './client'

export const getEvents = () => get('/api/events')
export const getEvent = (folder) => get(`/api/events/${folder}`)
