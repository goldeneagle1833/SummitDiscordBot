import { useState, useEffect } from 'react'
import { fetchAdmins, addAdmin, removeAdmin } from '@/api/explorer'

export default function ExplorerAdminPanel() {
  const [admins, setAdmins] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [discordId, setDiscordId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState(null)

  const load = () => {
    setLoading(true)
    fetchAdmins()
      .then(setAdmins)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleAdd = async (e) => {
    e.preventDefault()
    if (!discordId.trim()) return
    setAdding(true)
    setAddError(null)
    try {
      await addAdmin(discordId.trim(), displayName.trim() || null)
      setDiscordId('')
      setDisplayName('')
      load()
    } catch (err) {
      setAddError(err.message)
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (id) => {
    if (!confirm('Remove this admin?')) return
    try {
      await removeAdmin(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h3 className="text-base font-semibold text-text-primary mb-3">Explorer Admins</h3>

      {error && <p className="text-xs text-red-400 mb-2">{error}</p>}

      {loading ? (
        <p className="text-sm text-text-muted">Loading...</p>
      ) : (
        <div className="mb-4 space-y-1">
          {admins.length === 0 ? (
            <p className="text-sm text-text-muted">No Explorer admins yet.</p>
          ) : (
            admins.map((a) => (
              <div key={a.discord_user_id} className="flex items-center justify-between py-1.5 border-b border-border/40">
                <div>
                  <span className="text-sm text-text-primary font-medium">{a.display_name || a.discord_user_id}</span>
                  {a.display_name && (
                    <span className="text-xs text-text-muted ml-2">{a.discord_user_id}</span>
                  )}
                </div>
                <button
                  onClick={() => handleRemove(a.discord_user_id)}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors px-2 py-0.5"
                >
                  Remove
                </button>
              </div>
            ))
          )}
        </div>
      )}

      <form onSubmit={handleAdd} className="space-y-2">
        <p className="text-xs text-text-muted font-medium uppercase tracking-wide">Add Admin</p>
        <input
          type="text"
          value={discordId}
          onChange={(e) => setDiscordId(e.target.value)}
          placeholder="Discord User ID"
          className="w-full bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm"
          required
        />
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Display Name (optional)"
          className="w-full bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm"
        />
        {addError && <p className="text-xs text-red-400">{addError}</p>}
        <button
          type="submit"
          disabled={adding || !discordId.trim()}
          className="px-3 py-1.5 text-sm bg-primary/20 text-primary hover:bg-primary/30 rounded transition-colors disabled:opacity-40"
        >
          {adding ? 'Adding...' : 'Add Admin'}
        </button>
      </form>
    </div>
  )
}
