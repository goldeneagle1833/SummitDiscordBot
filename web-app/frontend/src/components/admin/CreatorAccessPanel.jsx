import { useEffect, useRef, useState } from 'react'
import { getCreatorAccess, addCreatorAccess, removeCreatorAccess, searchUsers } from '@/api/admin'

/**
 * Grant or revoke the creator role. Moved here from the old Popular Cards
 * page when it merged into Card Stats; the role no longer gates any page.
 */
export default function CreatorAccessPanel() {
  // Admin: creator access management
  const [accessList, setAccessList] = useState([])
  const [accessLoading, setAccessLoading] = useState(false)
  const [userQuery, setUserQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [actionMsg, setActionMsg] = useState(null)
  const searchTimeout = useRef(null)

  useEffect(() => {
    setAccessLoading(true)
    getCreatorAccess()
      .then((d) => setAccessList(d.users || []))
      .catch(() => {})
      .finally(() => setAccessLoading(false))
  }, [])

  const handleUserSearch = (q) => {
    setUserQuery(q)
    setSearchResults([])
    clearTimeout(searchTimeout.current)
    if (q.length < 2) return
    searchTimeout.current = setTimeout(() => {
      setSearching(true)
      searchUsers(q)
        .then((d) => setSearchResults(d.users || []))
        .catch(() => {})
        .finally(() => setSearching(false))
    }, 300)
  }

  const handleAdd = async (u) => {
    setActionMsg(null)
    try {
      await addCreatorAccess(u.user_id, u.display_name)
      setAccessList((prev) => [...prev, { user_id: u.user_id, display_name: u.display_name }].sort((a, b) => a.display_name.localeCompare(b.display_name)))
      setUserQuery('')
      setSearchResults([])
      setActionMsg({ type: 'ok', text: `Added ${u.display_name}` })
    } catch {
      setActionMsg({ type: 'err', text: 'Failed to add user' })
    }
  }

  const handleRemove = async (userId, displayName) => {
    setActionMsg(null)
    try {
      await removeCreatorAccess(userId)
      setAccessList((prev) => prev.filter((u) => u.user_id !== userId))
      setActionMsg({ type: 'ok', text: `Removed ${displayName}` })
    } catch {
      setActionMsg({ type: 'err', text: 'Failed to remove user' })
    }
  }

  return (
        <div className="border border-border rounded-lg p-5 bg-bg-raised">
          <h2 className="text-base font-semibold text-text-primary mb-1">Creator Access</h2>
          <p className="text-xs text-text-muted mb-4">
            Grant or revoke the creator role for specific users. Card Stats is public, so this no longer gates any page.
          </p>

          {actionMsg && (
            <p className={`text-xs mb-3 ${actionMsg.type === 'ok' ? 'text-accent-green' : 'text-accent-red'}`}>
              {actionMsg.text}
            </p>
          )}

          {/* User search */}
          <div className="mb-4 relative">
            <input
              type="text"
              value={userQuery}
              onChange={(e) => handleUserSearch(e.target.value)}
              placeholder="Search users to add..."
              className="w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm"
            />
            {(searching || searchResults.length > 0) && userQuery.length >= 2 && (
              <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-bg-surface border border-border rounded shadow-lg">
                {searching && <p className="text-xs text-text-muted px-3 py-2">Searching...</p>}
                {!searching && searchResults.length === 0 && (
                  <p className="text-xs text-text-muted px-3 py-2">No users found</p>
                )}
                {searchResults.map((u) => {
                  const alreadyAdded = accessList.some((a) => a.user_id === u.user_id)
                  return (
                    <div key={u.user_id} className="flex items-center justify-between px-3 py-2 hover:bg-bg-raised border-b border-border/50 last:border-0">
                      <span className="text-sm">{u.display_name}</span>
                      <button
                        onClick={() => !alreadyAdded && handleAdd(u)}
                        disabled={alreadyAdded}
                        className="text-xs px-2 py-1 rounded bg-primary text-bg disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
                      >
                        {alreadyAdded ? 'Already added' : 'Add'}
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Current access list */}
          {accessLoading && <p className="text-xs text-text-muted">Loading...</p>}
          {!accessLoading && accessList.length === 0 && (
            <p className="text-xs text-text-muted">No users have been manually granted access.</p>
          )}
          {!accessLoading && accessList.length > 0 && (
            <ul className="space-y-1">
              {accessList.map((u) => (
                <li key={u.user_id} className="flex items-center justify-between text-sm py-1.5 border-b border-border/30 last:border-0">
                  <span>{u.display_name}</span>
                  <button
                    onClick={() => handleRemove(u.user_id, u.display_name)}
                    className="text-xs text-accent-red hover:opacity-80"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
  )
}
