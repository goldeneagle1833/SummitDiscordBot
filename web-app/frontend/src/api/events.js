import { get, post, put } from './client'

export const getEvents = () => get('/api/top-8-events').then((data) => data.events || data)
export const getEventsWithAdmin = () => get('/api/top-8-events')
export const getEvent = (folder) => get(`/api/events/${folder}`)
export const reorderEvents = (order) => post('/api/events/reorder', { order })
export const updateEventMetadata = (folder, { name, rating, description }) =>
  put(`/api/events/${folder}/metadata`, { name, rating, description })
