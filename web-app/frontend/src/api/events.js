import { get, post, put } from './client'

export const getEvents = () => get('/api/top-8-events').then((data) => data.events || data)
export const getEventsWithAdmin = () => get('/api/top-8-events')
export const getEvent = (folder) => get(`/api/events/${folder}`)
export const reorderEvents = (order) => post('/api/events/reorder', { order })
export const updateEventMetadata = (folder, { name, rating, description }) =>
  put(`/api/events/${folder}/metadata`, { name, rating, description })
export const createEvent = ({ title, ranked_urls, bulk_urls }) =>
  post('/api/events/create', { title, ranked_urls, bulk_urls })
export const updateEventDecks = (folder, { table, mode, urls }) =>
  post(`/api/events/${folder}/decks`, { table, mode, urls })
export const refreshEvent = (folder) => post(`/api/events/${folder}/refresh`)
