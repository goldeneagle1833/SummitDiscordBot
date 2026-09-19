import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import {
  getUserProfiles,
  getUserProfileCandidates,
  addUserProfile,
  deleteUserProfile,
} from '@/api/admin'

const PAGE_SIZE = 50
const DISCORD_ID_RE = /^\d{15,25}$/

function avatarUrl(profile) {
  if (!profile.avatar) return null
  if (profile.avatar.startsWith('http')) return profile.avatar
  return `https://cdn.discordapp.com/avatars/${profile.user_id}/${profile.avatar}.png?size=32`
}

function formatDate(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString()
}

function AddUserForm({ onAdded }) {
  const [name, setName] = useState('')
  const [userId, setUserId] = useState('')
  const [avatar, setAvatar] = useState('')
  const [candidates, setCandidates] = useState([])
  const [searching, setSearching] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const timerRef = useRef(null)

  const lookup = useCallback(async (q) => {
    setSearching(true)
    try {
      const data = await getUserProfileCandidates(q)
      setCandidates(data.candidates || [])
    } catch {
      setCandidates([])
    }
    setSearching(false)
  }, [])

  const handleName = (e) => {
    const value = e.target.value
    setName(value)
    setResult(null)
    clearTimeout(timerRef.current)
    if (value.trim().length < 2) {
      setCandidates([])
      return
    }
    timerRef.current = setTimeout(() => lookup(value.trim()), 250)
  }

  useEffect(() => () => clearTimeout(timerRef.current), [])

  const useCandidate = (candidate) => {
    setName(candidate.display_name)
    setUserId(candidate.user_id)
    setCandidates([])
    setResult(null)
  }

  const idValid = DISCORD_ID_RE.test(userId.trim())
  const canSubmit = name.trim().length > 0 && idValid && !submitting

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setResult(null)
    try {
      const data = await addUserProfile(userId.trim(), name.trim(), avatar.trim() || null)
      setResult({ success: true, message: `Added ${data.profile?.display_name || name.trim()}` })
      setName('')
      setUserId('')
      setAvatar('')
      setCandidates([])
      onAdded?.()
    } catch (err) {
      setResult({ success: false, message: err.message || 'Request failed' })
    }
    setSubmitting(false)
  }

  return (
    <form onSubmit={handleSubmit} className="bg-bg-raised border border-border rounded-lg p-4 space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-1">
          <label htmlFor="discord-name" className="text-xs text-text-muted">Discord name</label>
          <input
            id="discord-name"
            type="text"
            value={name}
            onChange={handleName}
            placeholder="Start typing a Discord name..."
            autoComplete="off"
            spellCheck={false}
            className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="discord-id" className="text-xs text-text-muted">Discord user ID</label>
          <input
            id="discord-id"
            type="text"
            inputMode="numeric"
            value={userId}
            onChange={(e) => { setUserId(e.target.value); setResult(null) }}
            placeholder="e.g. 123456789012345678"
            autoComplete="off"
            className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
          />
          {userId.trim() && !idValid && (
            <p className="text-xs text-accent-red">Must be a numeric Discord ID (15–25 digits).</p>
          )}
        </div>
      </div>

      {name.trim().length >= 2 && (
        <div className="bg-bg-surface border border-border rounded">
          {searching ? (
            <div className="px-3 py-2 text-sm text-text-muted">Searching known players…</div>
          ) : candidates.length === 0 ? (
            <div className="px-3 py-2 text-sm text-text-muted">
              No known player matches “{name.trim()}” — enter their Discord ID manually below.
            </div>
          ) : (
            <ul>
              {candidates.map((c) => (
                <li key={c.user_id} className="flex items-center gap-2 px-3 py-2 text-sm border-b border-border last:border-b-0">
                  <span className="flex-1">{c.display_name}</span>
                  <span className="text-xs text-text-muted">{c.user_id}</span>
                  <span className="text-xs text-text-muted hidden sm:inline">{c.source}</span>
                  <button
                    type="button"
                    onClick={() => useCandidate(c)}
                    className="text-xs text-primary hover:underline"
                  >
                    Use
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="space-y-1">
        <label htmlFor="avatar-hash" className="text-xs text-text-muted">Avatar hash or URL (optional)</label>
        <input
          id="avatar-hash"
          type="text"
          value={avatar}
          onChange={(e) => setAvatar(e.target.value)}
          placeholder="Leave blank to use the default avatar"
          autoComplete="off"
          className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!canSubmit}
          className="px-4 py-2 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
        >
          {submitting ? 'Adding…' : 'Add User'}
        </button>
        <p className="text-xs text-text-muted">
          The profile is replaced by their real Discord details the first time they log in.
        </p>
      </div>

      {result && (
        <div
          role="status"
          className={`text-sm rounded p-3 border ${
            result.success
              ? 'bg-accent-green/10 border-accent-green/30 text-accent-green'
              : 'bg-accent-red/10 border-accent-red/30 text-accent-red'
          }`}
        >
          {result.message}
        </div>
      )}
    </form>
  )
}

function ProfileTable({ profiles, onRemove, removingId }) {
  if (profiles.length === 0) {
    return <p className="text-sm text-text-muted px-1 py-4">No user profiles found.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-muted border-b border-border">
            <th className="py-2 pr-3 font-normal">User</th>
            <th className="py-2 pr-3 font-normal">Discord ID</th>
            <th className="py-2 pr-3 font-normal">Provider</th>
            <th className="py-2 pr-3 font-normal">Status</th>
            <th className="py-2 pr-3 font-normal">Last login</th>
            <th className="py-2 font-normal" />
          </tr>
        </thead>
        <tbody>
          {profiles.map((p) => {
            const url = avatarUrl(p)
            const removable = p.manually_added && !p.has_logged_in
            return (
              <tr key={`${p.user_id}-${p.provider}`} className="border-b border-border/50">
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    {url ? (
                      <img src={url} alt="" className="w-6 h-6 rounded-full object-cover" onError={(e) => { e.target.style.visibility = 'hidden' }} />
                    ) : (
                      <span className="w-6 h-6 rounded-full bg-border/40 inline-block" />
                    )}
                    <Link to={`/player/${p.user_id}`} className="hover:text-primary transition-colors">
                      {p.custom_display_name || p.display_name}
                    </Link>
                  </div>
                </td>
                <td className="py-2 pr-3 text-xs text-text-muted">{p.user_id}</td>
                <td className="py-2 pr-3 text-xs text-text-muted">{p.provider}</td>
                <td className="py-2 pr-3 text-xs">
                  {removable ? (
                    <span className="text-amber-400">
                      Added by {p.manually_added_by || 'an admin'} — never logged in
                    </span>
                  ) : (
                    <span className="text-text-muted">Logged in</span>
                  )}
                </td>
                <td className="py-2 pr-3 text-xs text-text-muted">
                  {p.has_logged_in ? formatDate(p.last_login_at) : '—'}
                </td>
                <td className="py-2 text-right">
                  {removable && (
                    <button
                      onClick={() => onRemove(p)}
                      disabled={removingId === p.user_id}
                      className="text-xs text-accent-red hover:underline disabled:opacity-40"
                    >
                      {removingId === p.user_id ? 'Removing…' : 'Remove'}
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function UserProfiles() {
  usePageTitle('Admin Users')

  const [profiles, setProfiles] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [removingId, setRemovingId] = useState(null)
  const timerRef = useRef(null)

  const load = useCallback(async (query, pageIndex) => {
    setLoading(true)
    setError(null)
    try {
      const data = await getUserProfiles(query, PAGE_SIZE, pageIndex * PAGE_SIZE)
      setProfiles(data.profiles || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err.message || 'Failed to load user profiles')
      setProfiles([])
      setTotal(0)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    load(search, page)
  }, [load, search, page])

  const handleSearch = (e) => {
    const value = e.target.value
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setPage(0)
      setSearch(value.trim())
    }, 250)
  }

  useEffect(() => () => clearTimeout(timerRef.current), [])

  const handleRemove = async (profile) => {
    if (!confirm(`Remove the profile for "${profile.display_name}" (${profile.user_id})?`)) return
    setRemovingId(profile.user_id)
    try {
      await deleteUserProfile(profile.user_id)
      await load(search, page)
    } catch (err) {
      setError(err.message || 'Failed to remove profile')
    }
    setRemovingId(null)
  }

  const refresh = () => load(search, page)
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display text-secondary">Users</h1>
        <p className="text-sm text-text-muted">
          Add a website profile for a Discord player before their first login, so they are
          searchable and linkable across the site.
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-display text-secondary">Add User</h2>
        <AddUserForm onAdded={refresh} />
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-display text-secondary">
            Existing Profiles <span className="text-sm text-text-muted">({total})</span>
          </h2>
          <input
            type="search"
            onChange={handleSearch}
            placeholder="Filter by name or ID..."
            aria-label="Filter profiles"
            className="bg-bg-surface border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
          />
        </div>

        {error && (
          <div className="text-sm rounded p-3 border bg-accent-red/10 border-accent-red/30 text-accent-red">
            {error}
          </div>
        )}

        <div className="bg-bg-raised border border-border rounded-lg p-4">
          {loading ? (
            <p className="text-sm text-text-muted py-4">Loading…</p>
          ) : (
            <ProfileTable profiles={profiles} onRemove={handleRemove} removingId={removingId} />
          )}
        </div>

        {lastPage > 0 && (
          <div className="flex items-center gap-3 text-sm">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1 border border-border rounded disabled:opacity-40"
            >
              Previous
            </button>
            <span className="text-text-muted">Page {page + 1} of {lastPage + 1}</span>
            <button
              onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
              disabled={page >= lastPage}
              className="px-3 py-1 border border-border rounded disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
