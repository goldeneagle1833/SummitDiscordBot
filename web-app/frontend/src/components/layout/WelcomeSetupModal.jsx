import { useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { finishWelcome } from '@/api/auth'
import { setDisplayName, setShowcase } from '@/api/players'
import { CardSearch } from '@/components/player/ShowcaseModal'

const NAME_RE = /^[\w\s.-]+$/
const inputCls = 'w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm focus:border-secondary/70 outline-none'

/**
 * First sign-in with an emailed code: a new account starts as "Player 1234",
 * so ask what to call them and (optionally) their favorite card. Shown once;
 * "Not now" keeps the default name, which they can change on their profile.
 */
export default function WelcomeSetupModal() {
  const { user, setUser, refreshUser } = useAuth()
  const [name, setName] = useState('')
  const [card, setCard] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  if (!user || !user.needs_welcome) return null

  const close = async () => {
    setUser({ ...user, needs_welcome: false })
    try {
      await finishWelcome()
    } catch {
      // Worst case it shows again next visit
    }
  }

  const save = async () => {
    const trimmed = name.trim()
    if (!trimmed || trimmed.length > 32) {
      setError('Pick a username of 1 to 32 characters.')
      return
    }
    if (!NAME_RE.test(trimmed)) {
      setError('Use letters, numbers, spaces, hyphens, underscores and periods.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await setDisplayName(user.user_id, trimmed)
      if (card) await setShowcase(user.user_id, { favorite_card: card.name })
      await finishWelcome().catch(() => {})
      await refreshUser()
      setUser((u) => (u ? { ...u, needs_welcome: false } : u))
      // Their own profile page was showing the old name and no card
      if (window.location.pathname.startsWith(`/player/${user.user_id}`)) window.location.reload()
    } catch (err) {
      setError(err.message || 'Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-start sm:items-center justify-center bg-black/60 overflow-y-auto">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-title"
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4 my-6"
      >
        <h3 id="welcome-title" className="text-lg font-semibold text-text-primary mb-1">
          Welcome to Sorcerers Summit
        </h3>
        <p className="text-sm text-text-muted mb-5">
          Set up your account. Your username shows on the leaderboard, match history and your profile.
        </p>

        <label htmlFor="welcome-name" className="block text-xs text-text-muted mb-1">Username</label>
        <input
          id="welcome-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !saving && save()}
          maxLength={32}
          placeholder={user.username || 'Your username'}
          className={inputCls}
          autoComplete="nickname"
          autoFocus
        />
        <p className="text-xs text-text-muted mt-1 mb-5">1 to 32 characters. You can change it later on your profile.</p>

        <label htmlFor="welcome-card" className="block text-xs text-text-muted mb-1">
          Favorite card <span className="text-text-muted/70">(optional)</span>
        </label>
        <CardSearch value={card} onChange={setCard} inputId="welcome-card" />
        <p className="text-xs text-text-muted mt-1 mb-5">Shown in a box on your profile.</p>

        {error && <p className="text-sm text-accent-red mb-3">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={close}
            disabled={saving}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40"
          >
            Not now
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="px-4 py-1.5 text-sm font-medium bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
