import { get, post, del } from './client'

export const getCommunity = () => get('/api/community')
export const addCommunityEntry = (data) => post('/api/community', data)
export const deleteCommunityEntry = (type, id) => del(`/api/community/${type}/${id}`)

/** Link previews (title, description, image) for deck links, keyed by URL. */
export const getDeckLinkPreviews = (urls) => {
  const params = new URLSearchParams()
  for (const u of urls) params.append('url', u)
  return get(`/api/link-previews/decks?${params}`)
}
