import { useState, useEffect, useRef, useCallback } from 'react'
import { get, post } from '@/api/client'

function PlayerSearchInput({ label, selected, onSelect, onClear }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const timerRef = useRef(null)
  const containerRef = useRef(null)

  const search = useCallback(async (q) => {
    if (q.length < 2) { setOpen(false); return }
    try {
      const data = await get(`/api/admin/search-users?q=${encodeURIComponent(q)}`)
      setResults(data.users || [])
      setActiveIdx(-1)
      setOpen(true)
    } catch {
      setOpen(false)
    }
  }, [])

  const handleInput = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(timerRef.current)
    if (val.trim().length < 2) { setOpen(false); return }
    timerRef.current = setTimeout(() => search(val.trim()), 200)
  }

  const pick = (user) => {
    setOpen(false)
    setQuery('')
    onSelect(user)
  }

  const handleKeyDown = (e) => {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (activeIdx >= 0 && results[activeIdx]) pick(results[activeIdx])
      else if (results.length === 1) pick(results[0])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const getAvatarUrl = (user) => {
    if (user.provider === 'discord' && user.avatar)
      return `https://cdn.discordapp.com/avatars/${user.user_id}/${user.avatar}.png?size=32`
    if (user.provider === 'google' && user.avatar) return user.avatar
    return null
  }

  if (selected) {
    const avatarUrl = getAvatarUrl(selected)
    return (
      <div className="space-y-1">
        <label className="text-xs text-text-muted">{label}</label>
        <div className="flex items-center gap-2 bg-bg-surface border border-border rounded px-3 py-2">
          {avatarUrl ? (
            <img src={avatarUrl} alt="" className="w-6 h-6 rounded-full object-cover" onError={(e) => { e.target.style.visibility = 'hidden' }} />
          ) : (
            <span className="w-6 h-6 rounded-full bg-border/40 inline-block" />
          )}
          <span className="text-sm flex-1">{selected.display_name}</span>
          <span className="text-xs text-text-muted">{selected.user_id}</span>
          <button onClick={onClear} className="text-xs text-accent-red hover:underline ml-2">Clear</button>
        </div>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative space-y-1">
      <label className="text-xs text-text-muted">{label}</label>
      <input
        type="text"
        value={query}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder="Search by name..."
        autoComplete="off"
        spellCheck={false}
        className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary/60 placeholder:text-text-muted"
      />
      {open && (
        <div className="absolute z-50 w-full mt-1 bg-bg-surface border border-border rounded shadow-lg overflow-hidden">
          {results.length === 0 ? (
            <div className="px-4 py-2 text-sm text-text-muted">No users found</div>
          ) : (
            results.map((user, i) => {
              const avatarUrl = getAvatarUrl(user)
              return (
                <button
                  key={user.user_id}
                  onClick={() => pick(user)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-bg-elevated transition-colors ${i === activeIdx ? 'bg-bg-elevated' : ''}`}
                >
                  {avatarUrl ? (
                    <img src={avatarUrl} alt="" className="w-6 h-6 rounded-full object-cover" onError={(e) => { e.target.style.visibility = 'hidden' }} />
                  ) : (
                    <span className="w-6 h-6 rounded-full bg-border/40 inline-block" />
                  )}
                  <span className="flex-1">{user.display_name}</span>
                  <span className="text-xs text-text-muted">{user.user_id}</span>
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}

export default function TransferHistorySection({ onRefresh }) {
  const [oldUser, setOldUser] = useState(null)
  const [newUser, setNewUser] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const handleTransfer = async () => {
    if (!oldUser || !newUser) return
    if (oldUser.user_id === newUser.user_id) {
      alert('Source and destination accounts cannot be the same.')
      return
    }
    if (!confirm(
      `Transfer ALL history from "${oldUser.display_name}" (${oldUser.user_id}) to "${newUser.display_name}" (${newUser.user_id})?\n\nThis will update all match records, ELO standings, and other data. This action is difficult to reverse.`
    )) return

    setLoading(true)
    setResult(null)
    try {
      const data = await post('/api/admin/transfer-history', {
        old_user_id: oldUser.user_id,
        new_user_id: newUser.user_id,
      })
      setResult(data)
      if (data.success) {
        onRefresh?.()
      }
    } catch (err) {
      setResult({ success: false, error: err.message || 'Request failed' })
    }
    setLoading(false)
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-text-primary">Transfer Account History</h2>
        <p className="text-xs text-text-muted">Move all match history, ELO, and data from one account to another</p>
      </div>

      <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <PlayerSearchInput
            label="Source Account (old)"
            selected={oldUser}
            onSelect={setOldUser}
            onClear={() => { setOldUser(null); setResult(null) }}
          />
          <PlayerSearchInput
            label="Destination Account (new)"
            selected={newUser}
            onSelect={setNewUser}
            onClear={() => { setNewUser(null); setResult(null) }}
          />
        </div>

        {oldUser && newUser && oldUser.user_id === newUser.user_id && (
          <p className="text-xs text-accent-red">Source and destination cannot be the same account.</p>
        )}

        <button
          onClick={handleTransfer}
          disabled={loading || !oldUser || !newUser || oldUser.user_id === newUser.user_id}
          className="px-4 py-2 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
        >
          {loading ? 'Transferring...' : 'Transfer History'}
        </button>

        {result && (
          <div className={`text-sm rounded p-3 border ${result.success ? 'bg-accent-green/10 border-accent-green/30 text-accent-green' : 'bg-accent-red/10 border-accent-red/30 text-accent-red'}`}>
            {result.success ? (
              <div className="space-y-1">
                <div className="font-semibold">{result.message}</div>
                {result.details && Object.keys(result.details).length > 0 && (
                  <ul className="text-xs space-y-0.5 mt-1">
                    {Object.entries(result.details).map(([table, count]) => (
                      <li key={table}>
                        <span className="text-text-muted">{table}:</span> {typeof count === 'number' ? `${count} rows` : count}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <span>{result.error}</span>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
