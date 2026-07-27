import { useState, useEffect, useMemo, useRef } from 'react'
import { getBlockedUsers, blockUser, unblockUser, searchPlayers } from '@/api/players'

export default function BlockListModal({ playerId, onClose }) {
  const [blockedUsers, setBlockedUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [actionInProgress, setActionInProgress] = useState(null)
  const [pendingBlock, setPendingBlock] = useState(null)
  const [reason, setReason] = useState('')
  const searchTimeout = useRef(null)
  const requestSeqRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const load = async () => {
      try {
        const data = await getBlockedUsers(playerId)
        if (!cancelled) setBlockedUsers(data.blocked_users)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load block list')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [playerId])

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  // Clean up pending search work on unmount
  useEffect(() => () => {
    clearTimeout(searchTimeout.current)
    requestSeqRef.current++
  }, [])

  const handleSearch = (query) => {
    setSearchQuery(query)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)

    if (query.length < 2) {
      requestSeqRef.current++ // invalidate in-flight requests
      setSearchResults([])
      setSearching(false)
      return
    }

    searchTimeout.current = setTimeout(async () => {
      const seq = ++requestSeqRef.current
      setSearching(true)
      try {
        const data = await searchPlayers(query)
        if (seq !== requestSeqRef.current) return // stale response
        setSearchResults(data.players)
      } catch {
        if (seq === requestSeqRef.current) setSearchResults([])
      } finally {
        if (seq === requestSeqRef.current) setSearching(false)
      }
    }, 300)
  }

  // Filter out self and already-blocked users at render time so the list
  // stays correct even when blockedUsers changes after the search resolved.
  const visibleResults = useMemo(() => {
    const blockedIds = new Set(blockedUsers.map((u) => u.user_id))
    return searchResults.filter(
      (p) => p.user_id !== playerId && !blockedIds.has(p.user_id)
    )
  }, [searchResults, blockedUsers, playerId])

  const handleConfirmBlock = async () => {
    if (!pendingBlock || !reason.trim()) return
    setActionInProgress(pendingBlock.user_id)
    setError(null)
    try {
      await blockUser(playerId, pendingBlock.user_id, reason.trim())
      setBlockedUsers((prev) => [
        { user_id: pendingBlock.user_id, display_name: pendingBlock.display_name, avatar: pendingBlock.avatar, reason: reason.trim() },
        ...prev,
      ])
      setSearchResults([])
      setSearchQuery('')
      setPendingBlock(null)
      setReason('')
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
        role="dialog"
        aria-modal="true"
        aria-labelledby="block-list-title"
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="block-list-title" className="text-lg font-semibold text-text-primary mb-1">Block List</h3>
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
            aria-label="Search players to block"
            className="w-full px-3 py-2 text-sm rounded border border-border bg-bg-raised text-text-primary placeholder-text-muted focus:outline-none focus:border-secondary/50"
          />
          {searching && <p className="text-xs text-text-muted mt-1">Searching...</p>}
          {visibleResults.length > 0 && !pendingBlock && (
            <div className="mt-1 max-h-36 overflow-y-auto border border-border rounded bg-bg-raised">
              {visibleResults.map((user) => (
                <div
                  key={user.user_id}
                  className="flex items-center justify-between px-3 py-2 hover:bg-bg-surface/50 transition-colors"
                >
                  <span className="text-sm text-text-primary truncate">{user.display_name}</span>
                  <button
                    onClick={() => setPendingBlock(user)}
                    className="text-xs px-2 py-1 rounded bg-accent-red/20 text-accent-red hover:bg-accent-red/30 shrink-0 ml-2"
                  >
                    Block
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Reason prompt when blocking */}
        {pendingBlock && (
          <div className="mb-4 p-3 rounded border border-accent-red/30 bg-accent-red/5">
            <p className="text-sm text-text-primary mb-2">
              Block <span className="font-semibold">{pendingBlock.display_name}</span>?
            </p>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason (required)"
              aria-label="Reason for blocking"
              aria-required="true"
              maxLength={200}
              className="w-full px-3 py-2 text-sm rounded border border-border bg-bg-raised text-text-primary placeholder-text-muted focus:outline-none focus:border-secondary/50 mb-2"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setPendingBlock(null); setReason('') }}
                className="text-xs px-3 py-1 rounded border border-border text-text-muted hover:text-text-primary"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmBlock}
                disabled={actionInProgress === pendingBlock.user_id || !reason.trim()}
                className="text-xs px-3 py-1 rounded bg-accent-red/20 text-accent-red hover:bg-accent-red/30 disabled:opacity-50"
              >
                {actionInProgress === pendingBlock.user_id ? '...' : 'Confirm Block'}
              </button>
            </div>
          </div>
        )}

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
              <div className="min-w-0">
                <span className="text-sm text-text-primary truncate block">{user.display_name}</span>
                {user.reason && (
                  <span className="text-xs text-text-muted truncate block">{user.reason}</span>
                )}
              </div>
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
