// Site session bootstrap.
//
// Every /api/* request is gated server-side (web-app/utils/site_gate.py):
// it must carry an API key or the site token the server hands to our own
// pages.  The token lives in an HttpOnly cookie set by GET /api/site-token,
// so this module only has to make sure that request has happened before any
// other API call goes out.  Nothing secret ever reaches JavaScript.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const TOKEN_URL = `${API_BASE_URL}/api/site-token`

let sessionPromise = null

async function requestToken() {
  const res = await fetch(TOKEN_URL, { credentials: 'include', cache: 'no-store' })
  if (!res.ok) throw new Error(`site-token ${res.status}`)
  return true
}

/** Resolve once the site token cookie is in place. Safe to call repeatedly. */
export function ensureSiteSession() {
  if (!sessionPromise) {
    sessionPromise = requestToken().catch((err) => {
      sessionPromise = null // let the next caller retry
      throw err
    })
  }
  return sessionPromise
}

/** Drop the cached bootstrap and fetch a fresh token (after a gate 401). */
export function refreshSiteSession() {
  sessionPromise = null
  return ensureSiteSession()
}

/** True when a response is the gate saying "no key / no site token". */
export function isGateRejection(res, data) {
  return res.status === 401 && data?.code === 'api_key_required'
}
