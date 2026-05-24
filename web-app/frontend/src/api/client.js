const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function request(method, url, body) {
  const options = {
    method,
    credentials: 'include',
    headers: {},
  }
  if (body) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }
  const res = await fetch(`${API_BASE_URL}${url}`, options)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const msg = data.error?.message || data.error || res.statusText
    throw new ApiError(res.status, msg)
  }
  return res.json()
}

export const get = (url) => request('GET', url)
export const post = (url, body) => request('POST', url, body)
export const put = (url, body) => request('PUT', url, body)
export const del = (url) => request('DELETE', url)
