import { get, post, put, del } from './client'

export const getEvents = () => get('/api/top-8-events').then((data) => data.events || data)
export const getEventsWithAdmin = () => get('/api/top-8-events')
export const getEvent = (folder) => get(`/api/events/${folder}`)
export const reorderEvents = (order) => post('/api/events/reorder', { order })
export const updateEventMetadata = (folder, { name, rating, description, event_date }) =>
  put(`/api/events/${folder}/metadata`, { name, rating, description, event_date })
export const createEvent = ({ title, ranked_urls, bulk_urls }) =>
  post('/api/events/create', { title, ranked_urls, bulk_urls })
export const updateEventDecks = (folder, { table, mode, urls }) =>
  post(`/api/events/${folder}/decks`, { table, mode, urls })
export const refreshEvent = (folder) => post(`/api/events/${folder}/refresh`)
export const deleteEvent = (folder) => del(`/api/events/${folder}`)
export const setFeaturedEvent = (folder) => put('/api/events/featured', { folder })
export const getEventJobStatus = (jobId) => get(`/api/events/jobs/${jobId}`)

/**
 * Poll a background event job until it completes or fails.
 * Calls onProgress(progress) on each poll, returns the final result.
 */
export const pollEventJob = async (jobId, { interval = 3000, onProgress } = {}) => {
  while (true) {
    const data = await getEventJobStatus(jobId)
    if (data.status === 'completed' || data.status === 'failed') {
      return data.result
    }
    if (onProgress && data.progress) onProgress(data.progress)
    await new Promise((r) => setTimeout(r, interval))
  }
}
