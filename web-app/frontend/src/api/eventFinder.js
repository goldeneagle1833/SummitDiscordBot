import { get, post, put, del } from './client'

// Find a player at an in-person event
export const getFinderMaps = () => get('/api/event-finder/maps')
export const getMapPeople = (mapId) => get(`/api/event-finder/maps/${mapId}/people`)
export const getFinderPerson = (token) => get(`/api/event-finder/p/${encodeURIComponent(token)}`)

export const getMyFinder = () => get('/api/event-finder/me')
export const updateMyFinder = (fields) => put('/api/event-finder/me', fields)
export const newFinderLink = () => post('/api/event-finder/me/new-link')
export const myFinderQrUrl = (bust = '', download = false) =>
  `/api/event-finder/me/qr.png?${download ? 'download=1&' : ''}v=${encodeURIComponent(bust)}`

export const createFinderMap = (fields) => post('/api/event-finder/admin/maps', fields)
export const updateFinderMap = (id, fields) => put(`/api/event-finder/admin/maps/${id}`, fields)
export const deleteFinderMap = (id) => del(`/api/event-finder/admin/maps/${id}`)
export const uploadFinderMapImage = (file) => {
  const fd = new FormData()
  fd.append('image', file)
  return fetch('/api/event-finder/admin/maps/upload-image', {
    method: 'POST',
    body: fd,
    credentials: 'include',
  }).then(async (res) => {
    const d = await res.json().catch(() => ({}))
    if (res.status === 413) throw new Error('That image is too big. Try a smaller file.')
    if (!res.ok || !d.url) throw new Error(d.error || res.statusText)
    return d.url
  })
}

// "5 min ago" style freshness for a pin
export function timeAgo(iso, now = Date.now()) {
  if (!iso) return ''
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const mins = Math.max(0, Math.round((now - then) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  const rest = mins % 60
  if (hours < 24) return rest ? `${hours} h ${rest} min ago` : `${hours} h ago`
  return `${Math.floor(hours / 24)} d ago`
}

export function closedMessage(reason, map) {
  switch (reason) {
    case 'off':
      return 'isn’t sharing their spot right now.'
    case 'before':
      return map ? `will share their spot once ${map.name} starts.` : 'isn’t sharing yet.'
    case 'after':
      return 'isn’t sharing. The event is over.'
    case 'closed_today':
      return map
        ? `isn’t sharing right now. Spots show ${fmtHour(map.daily_start)} to ${fmtHour(map.daily_end)} during the event.`
        : 'isn’t sharing right now.'
    default:
      return 'isn’t sharing their spot right now.'
  }
}

export function fmtHour(hm) {
  if (!hm) return ''
  const [h, m] = hm.split(':').map(Number)
  const suffix = h >= 12 ? 'p.m.' : 'a.m.'
  const h12 = h % 12 || 12
  return m ? `${h12}:${String(m).padStart(2, '0')} ${suffix}` : `${h12} ${suffix}`
}
