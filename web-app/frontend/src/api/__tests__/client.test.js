import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Must mock before importing
vi.stubGlobal('fetch', vi.fn())

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
})
