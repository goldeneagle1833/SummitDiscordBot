import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Must mock before importing
vi.stubGlobal('fetch', vi.fn())

// The site-session bootstrap is covered by siteSession.test.js; here we
// stub it so each test's fetch mock queue only sees the request under test.
const siteSession = { ensure: vi.fn(() => Promise.resolve(true)), refresh: vi.fn(() => Promise.resolve(true)) }
vi.mock('../siteSession', async () => {
  const actual = await vi.importActual('../siteSession')
  return {
    ...actual,
    ensureSiteSession: (...a) => siteSession.ensure(...a),
    refreshSiteSession: (...a) => siteSession.refresh(...a),
  }
})

// Dynamic import so import.meta.env is available
let get, post, put, del, ApiError
beforeEach(async () => {
  vi.resetModules()
  const client = await import('../client')
  get = client.get
  post = client.post
  put = client.put
  del = client.del
  ApiError = client.ApiError
})

afterEach(() => {
  vi.restoreAllMocks()
  siteSession.ensure.mockClear()
  siteSession.refresh.mockClear()
})

function mockFetchResponse(body, status = 200) {
  fetch.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? 'Not Found' : 'OK',
    json: () => Promise.resolve(body),
  })
}

describe('API client', () => {
  it('GET sends a GET request and returns JSON', async () => {
    mockFetchResponse({ data: 'test' })
    const result = await get('/api/test')
    expect(result).toEqual({ data: 'test' })
    expect(fetch).toHaveBeenCalledWith('/api/test', expect.objectContaining({ method: 'GET' }))
  })

  it('POST sends body as JSON', async () => {
    mockFetchResponse({ success: true })
    await post('/api/test', { name: 'foo' })
    const [, options] = fetch.mock.calls[0]
    expect(options.method).toBe('POST')
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual({ name: 'foo' })
  })

  it('PUT sends body as JSON', async () => {
    mockFetchResponse({ updated: true })
    await put('/api/test', { value: 1 })
    const [, options] = fetch.mock.calls[0]
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({ value: 1 })
  })

  it('DELETE sends a DELETE request', async () => {
    mockFetchResponse({ deleted: true })
    await del('/api/test')
    expect(fetch).toHaveBeenCalledWith('/api/test', expect.objectContaining({ method: 'DELETE' }))
  })

  it('includes credentials for cookie auth', async () => {
    mockFetchResponse({})
    await get('/api/test')
    const [, options] = fetch.mock.calls[0]
    expect(options.credentials).toBe('include')
  })

  it('throws ApiError with status on non-ok response', async () => {
    mockFetchResponse({ error: 'Not found' }, 404)
    try {
      await get('/api/missing')
      expect.fail('should have thrown')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect(err.status).toBe(404)
      expect(err.message).toBe('Not found')
    }
  })

  it('throws ApiError with statusText when JSON error body is missing', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.reject(new Error('no json')),
    })
    try {
      await get('/api/broken')
      expect.fail('should have thrown')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect(err.status).toBe(500)
      expect(err.message).toBe('Internal Server Error')
    }
  })

  it('bootstraps the site session before every request', async () => {
    mockFetchResponse({})
    await get('/api/test')
    expect(siteSession.ensure).toHaveBeenCalledTimes(1)
    expect(siteSession.refresh).not.toHaveBeenCalled()
  })

  it('refreshes the site token and retries once on a gate 401', async () => {
    mockFetchResponse({ error: 'An API key is required', code: 'api_key_required' }, 401)
    mockFetchResponse({ data: 'after-refresh' })
    const result = await get('/api/test')
    expect(result).toEqual({ data: 'after-refresh' })
    expect(siteSession.refresh).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('does not retry an ordinary 401 (e.g. not logged in)', async () => {
    mockFetchResponse({ error: 'Not authenticated' }, 401)
    await expect(get('/api/me')).rejects.toMatchObject({ status: 401, message: 'Not authenticated' })
    expect(siteSession.refresh).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('surfaces the gate error if the retry also fails', async () => {
    mockFetchResponse({ error: 'An API key is required', code: 'api_key_required' }, 401)
    mockFetchResponse({ error: 'An API key is required', code: 'api_key_required' }, 401)
    await expect(get('/api/test')).rejects.toMatchObject({ status: 401 })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
