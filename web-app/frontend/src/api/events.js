import { get, post } from './client'

export const getEvents = () => get('/api/top-8-events').then((data) => data.events || data)
export const getEventsWithAdmin = () => get('/api/top-8-events')
export const getEvent = (folder) => get(`/api/events/${folder}`)
export const reorderEvents = (order) => post('/api/events/reorder', { order })
