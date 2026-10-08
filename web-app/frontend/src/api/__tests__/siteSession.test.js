import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.stubGlobal('fetch', vi.fn())

let ensureSiteSession, refreshSiteSession, isGateRejection
beforeEach(async () => {
  vi.resetModules()
  fetch.mockReset()
  const mod = await import('../siteSession')
  ensureSiteSession = mod.ensureSiteSession
  refreshSiteSession = mod.refreshSiteSession
  isGateRejection = mod.isGateRejection
})

afterEach(() => vi.restoreAllMocks())

describe('siteSession', () => {
  it('requests /api/site-token once with credentials and caches the result', async () => {
    fetch.mockResolvedValue({ ok: true, status: 200 })
    await Promise.all([ensureSiteSession(), ensureSiteSession()])
    await ensureSiteSession()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/site-token', expect.objectContaining({ credentials: 'include' }))
  })

  it('retries the bootstrap on the next call after a failure', async () => {
    fetch.mockResolvedValueOnce({ ok: false, status: 503 })
    await expect(ensureSiteSession()).rejects.toThrow()
    fetch.mockResolvedValueOnce({ ok: true, status: 200 })
    await expect(ensureSiteSession()).resolves.toBe(true)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('refreshSiteSession always hits the server again', async () => {
    fetch.mockResolvedValue({ ok: true, status: 200 })
    await ensureSiteSession()
    await refreshSiteSession()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('isGateRejection only matches the gate 401', () => {
    expect(isGateRejection({ status: 401 }, { code: 'api_key_required' })).toBe(true)
    expect(isGateRejection({ status: 401 }, { error: 'Not authenticated' })).toBe(false)
    expect(isGateRejection({ status: 403 }, { code: 'api_key_required' })).toBe(false)
  })
})
