import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'

export default function Login() {
  usePageTitle('Login')
  const [searchParams] = useSearchParams()

  // Build the redirect-back URL: use ?next= param, or fallback to current origin
  const next = unwrapLoginNext(searchParams.get('next')) || window.location.origin + '/'
  const qs = `?next=${encodeURIComponent(next)}`

  return (
    <div className="max-w-sm mx-auto py-12 space-y-6 text-center">
      <h1 className="text-2xl font-display text-secondary">Login</h1>
      <p className="text-sm text-text-muted">
        Sign in to access your profile and track your stats.
      </p>
      <div className="space-y-3">
        <a
          href={`/auth/discord${qs}`}
          className="block w-full px-5 py-3 bg-[#5865F2] text-white rounded-soft font-medium hover:bg-[#4752C4] transition-colors"
        >
          Login with Discord
        </a>
        <a
          href={`/auth/google${qs}`}
          className="block w-full px-5 py-3 bg-bg-surface border border-border rounded-soft font-medium hover:border-primary/50 transition-colors"
        >
          Login with Google
        </a>
      </div>
      <div className="flex items-center gap-3 text-xs text-text-muted">
        <span className="flex-1 border-t border-border" />
        or
        <span className="flex-1 border-t border-border" />
      </div>
      <EmailCodeLogin next={next} />
    </div>
  )
}

async function postAuth(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok || !data.success) throw new Error(data.error || 'Something went wrong. Please try again.')
  return data
}

// No Discord or Google: we email a 6-digit code and the player types it back.
export function EmailCodeLogin({ next }) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [sentTo, setSentTo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const sendCode = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const data = await postAuth('/auth/email/start', { email, next })
      setSentTo(data.email)
      setCode('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const verify = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const data = await postAuth('/auth/email/verify', { email: sentTo, code })
      window.location.assign(data.redirect || '/')
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const inputCls = 'w-full px-4 py-3 bg-bg-surface border border-border rounded-soft focus:outline-none focus:border-primary/60'
  const buttonCls = 'block w-full px-5 py-3 bg-primary text-white rounded-soft font-medium hover:bg-primary/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed'

  if (!sentTo) {
    return (
      <form onSubmit={sendCode} className="space-y-3 text-left">
        <label htmlFor="login-email" className="block text-sm text-text-muted">Login with email</label>
        <input
          id="login-email"
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={inputCls}
        />
        <button type="submit" disabled={busy || !email} className={buttonCls}>
          {busy ? 'Sending…' : 'Email me a login code'}
        </button>
        {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      </form>
    )
  }

  return (
    <form onSubmit={verify} className="space-y-3 text-left">
      <p className="text-sm text-text-muted">
        We sent a 6-digit code to <span className="text-text">{sentTo}</span>. It works for 10 minutes.
      </p>
      <label htmlFor="login-code" className="block text-sm text-text-muted">Login code</label>
      <input
        id="login-code"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        placeholder="123456"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
        className={`${inputCls} text-center text-2xl tracking-[0.4em]`}
        autoFocus
      />
      <button type="submit" disabled={busy || code.length !== 6} className={buttonCls}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <button
        type="button"
        onClick={() => { setSentTo(null); setError(null) }}
        className="text-sm text-text-muted hover:text-secondary underline"
      >
        Use a different email or send a new code
      </button>
    </form>
  )
}

// A next= that points back at /login (from clicking Login while already on the
// login page) would nest forever: /login?next=/login?next=/login?next=...
// Peel those layers off and return the page the person actually came from.
export function unwrapLoginNext(next) {
  let value = next
  for (let i = 0; i < 20 && value; i++) {
    let url
    try {
      url = new URL(value, window.location.origin)
    } catch {
      return value
    }
    if (url.origin !== window.location.origin || url.pathname !== '/login') return value
    value = url.searchParams.get('next')
  }
  return value || null
}
