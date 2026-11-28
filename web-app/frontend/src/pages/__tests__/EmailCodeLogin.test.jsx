import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, userEvent, waitFor } from '@/test/test-utils'
import { EmailCodeLogin } from '../Login'

function reply(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

describe('EmailCodeLogin', () => {
  const assign = vi.fn()
  const realLocation = window.location

  beforeEach(() => {
    global.fetch = vi.fn()
    assign.mockReset()
    Object.defineProperty(window, 'location', { configurable: true, value: { ...realLocation, assign } })
  })
  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: realLocation })
  })

  it('emails a code, then signs in with it', async () => {
    fetch
      .mockReturnValueOnce(reply(200, { success: true, email: 'gee@example.com' }))
      .mockReturnValueOnce(reply(200, { success: true, redirect: '/player/1000000000000001' }))
    const user = userEvent.setup()
    render(<EmailCodeLogin next="https://sorcererssummit.com/" />)

    await user.type(screen.getByLabelText('Login with email'), 'Gee@Example.com')
    await user.click(screen.getByRole('button', { name: 'Email me a login code' }))

    expect(await screen.findByText('gee@example.com')).toBeInTheDocument()
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ email: 'Gee@Example.com', next: 'https://sorcererssummit.com/' })
    expect(fetch.mock.calls[0][0]).toBe('/auth/email/start')

    const signIn = screen.getByRole('button', { name: 'Sign in' })
    expect(signIn).toBeDisabled()
    await user.type(screen.getByLabelText('Login code'), '12a3456')
    await user.click(signIn)

    await waitFor(() => expect(assign).toHaveBeenCalledWith('/player/1000000000000001'))
    expect(fetch.mock.calls[1][0]).toBe('/auth/email/verify')
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ email: 'gee@example.com', code: '123456' })
  })

  it('shows the server message when a code is wrong', async () => {
    fetch
      .mockReturnValueOnce(reply(200, { success: true, email: 'gee@example.com' }))
      .mockReturnValueOnce(reply(400, { success: false, error: "That code isn't right. 4 tries left." }))
    const user = userEvent.setup()
    render(<EmailCodeLogin next="/" />)
    await user.type(screen.getByLabelText('Login with email'), 'gee@example.com')
    await user.click(screen.getByRole('button', { name: 'Email me a login code' }))
    await user.type(await screen.findByLabelText('Login code'), '000000')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("That code isn't right. 4 tries left.")
    expect(assign).not.toHaveBeenCalled()
  })

  it('says when email sign-in is not switched on', async () => {
    fetch.mockReturnValueOnce(reply(503, { success: false, error: "Email sign-in isn't switched on yet. Please use Discord or Google." }))
    const user = userEvent.setup()
    render(<EmailCodeLogin next="/" />)
    await user.type(screen.getByLabelText('Login with email'), 'gee@example.com')
    await user.click(screen.getByRole('button', { name: 'Email me a login code' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("isn't switched on yet")
  })
})
