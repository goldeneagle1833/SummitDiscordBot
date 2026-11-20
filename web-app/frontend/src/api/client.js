import { ensureSiteSession, refreshSiteSession, isGateRejection } from './siteSession'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function send(method, url, body) {
  const options = {
    method,
    credentials: 'include',
    headers: {},
  }
  if (body) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }
  return fetch(`${API_BASE_URL}${url}`, options)
}

async function request(method, url, body) {
  // The API gate needs the site token cookie; make sure it exists first.
  await ensureSiteSession().catch(() => {})

  let res = await send(method, url, body)
  if (!res.ok) {
    let data = await res.json().catch(() => ({}))
    if (isGateRejection(res, data)) {
      // Token expired or was cleared — fetch a new one and retry once.
      await refreshSiteSession().catch(() => {})
      res = await send(method, url, body)
      if (res.ok) return res.json()
      data = await res.json().catch(() => ({}))
    }
    const msg = data.error?.message || data.error || res.statusText
    throw new ApiError(res.status, msg)
  }
  return res.json()
}

/**
 * GET a file (zip, csv...) and return it as a Blob, with the server's
 * suggested file name. Same site-token retry as JSON requests.
 */
export async function getBlob(url) {
  await ensureSiteSession().catch(() => {})
  let res = await send('GET', url)
  if (!res.ok) {
    let data = await res.clone().json().catch(() => ({}))
    if (isGateRejection(res, data)) {
      await refreshSiteSession().catch(() => {})
      res = await send('GET', url)
      if (!res.ok) data = await res.json().catch(() => ({}))
    }
    if (!res.ok) {
      const msg = data.error?.message || data.error || res.statusText
      throw new ApiError(res.status, msg)
    }
  }
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
  return { blob: await res.blob(), filename: match ? decodeURIComponent(match[1]) : null }
}

export const get = (url) => request('GET', url)
export const post = (url, body) => request('POST', url, body)
export const put = (url, body) => request('PUT', url, body)
export const patch = (url, body) => request('PATCH', url, body)
export const del = (url) => request('DELETE', url)
