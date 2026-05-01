import { get } from './client'

export const getEvents = () => get('/api/top-8-events')
export const getEvent = (folder) => get(`/api/events/${folder}`)
