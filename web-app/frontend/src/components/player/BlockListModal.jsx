import { useState, useEffect, useRef } from 'react'
import { getBlockedUsers, blockUser, unblockUser, searchPlayers } from '@/api/players'

export default function BlockListModal({ playerId, onClose }) {
  const [blockedUsers, setBlockedUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [actionInProgress, setActionInProgress] = useState(null)
  const searchTimeout = useRef(null)

  useEffect(() => {
    loadBlockedUsers()
  }, [playerId])

  const loadBlockedUsers = async () => {
    try {
      const data = await getBlockedUsers(playerId)
      setBlockedUsers(data.blocked_users)
    } catch (err) {
      setError(err.message || 'Failed to load block list')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = (query) => {
    setSearchQuery(query)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)

    if (query.length < 2) {
      setSearchResults([])
      return
    }

    searchTimeout.current = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await searchPlayers(query)
        // Filter out self and already-blocked users
        const blockedIds = new Set(blockedUsers.map((u) => u.user_id))
        const filtered = data.players.filter(
          (p) => p.user_id !== playerId && !blockedIds.has(p.user_id)
        )
        setSearchResults(filtered)
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
  }

  const handleBlock = async (user) => {
    setActionInProgress(user.user_id)
    setError(null)
    try {
      await blockUser(playerId, user.user_id)
      setBlockedUsers((prev) => [
        { user_id: user.user_id, display_name: user.display_name, avatar: user.avatar },
        ...prev,
      ])
      setSearchResults((prev) => prev.filter((p) => p.user_id !== user.user_id))
      setSearchQuery('')
    } catch (err) {
      setError(err.message || 'Failed to block user')
    } finally {
      setActionInProgress(null)
    }
  }

  const handleUnblock = async (userId) => {
    setActionInProgress(userId)
    setError(null)
    try {
      await unblockUser(playerId, userId)
      setBlockedUsers((prev) => prev.filter((u) => u.user_id !== userId))
    } catch (err) {
      setError(err.message || 'Failed to unblock user')
    } finally {
      setActionInProgress(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text-primary mb-1">Block List</h3>
        <p className="text-xs text-text-muted mb-4">
          Blocked players will not be matched with you in the LFG queue.
        </p>

        {error && <p className="text-xs text-accent-red mb-3">{error}</p>}

        {/* Search to add */}
        <div className="mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search players to block..."
            className="w-full px-3 py-2 text-sm rounded border border-border bg-bg-raised text-text-primary placeholder-text-muted focus:outline-none focus:border-secondary/50"
          />
          {searching && <p className="text-xs text-text-muted mt-1">Searching...</p>}
          {searchResults.length > 0 && (
            <div className="mt-1 max-h-36 overflow-y-auto border border-border rounded bg-bg-raised">
              {searchResults.map((user) => (
                <div
                  key={user.user_id}
                  className="flex items-center justify-between px-3 py-2 hover:bg-bg-surface/50 transition-colors"
                >
                  <span className="text-sm text-text-primary truncate">{user.display_name}</span>
                  <button
                    onClick={() => handleBlock(user)}
                    disabled={actionInProgress === user.user_id}
                    className="text-xs px-2 py-1 rounded bg-accent-red/20 text-accent-red hover:bg-accent-red/30 disabled:opacity-50 shrink-0 ml-2"
                  >
                    {actionInProgress === user.user_id ? '...' : 'Block'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Current block list */}
        <div className="space-y-1 max-h-52 overflow-y-auto">
          {loading && <p className="text-sm text-text-muted text-center py-4">Loading...</p>}
          {!loading && blockedUsers.length === 0 && (
            <p className="text-sm text-text-muted text-center py-4">No blocked players.</p>
          )}
          {blockedUsers.map((user) => (
            <div
              key={user.user_id}
              className="flex items-center justify-between px-3 py-2 rounded bg-bg-raised border border-border"
            >
              <span className="text-sm text-text-primary truncate">{user.display_name}</span>
              <button
                onClick={() => handleUnblock(user.user_id)}
                disabled={actionInProgress === user.user_id}
                className="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-text-primary disabled:opacity-50 shrink-0 ml-2"
              >
                {actionInProgress === user.user_id ? '...' : 'Unblock'}
              </button>
            </div>
          ))}
        </div>

        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
