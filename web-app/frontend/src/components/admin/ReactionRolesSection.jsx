import { useState, useEffect, useCallback } from 'react'
import {
  getReactionRoleMessages,
  addReactionRoleMessage,
  deleteReactionRoleMessage,
  addReactionRoleMapping,
  deleteReactionRoleMapping,
} from '@/api/admin'
import Spinner from '@/components/ui/Spinner'

export default function ReactionRolesSection() {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Add message form
  const [showAddMsg, setShowAddMsg] = useState(false)
  const [newChannelId, setNewChannelId] = useState('')
  const [newMessageId, setNewMessageId] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [addMsgError, setAddMsgError] = useState(null)

  // Add mapping form (per message)
  const [addingTo, setAddingTo] = useState(null) // message_id currently adding to
  const [newEmoji, setNewEmoji] = useState('')
  const [newEmojiId, setNewEmojiId] = useState('')
  const [newRoleId, setNewRoleId] = useState('')
  const [newRoleName, setNewRoleName] = useState('')
  const [addMapError, setAddMapError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getReactionRoleMessages()
      .then(d => setMessages(d.messages ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const handleAddMessage = async (e) => {
    e.preventDefault()
    setAddMsgError(null)
    if (!newChannelId.trim() || !newMessageId.trim()) {
      setAddMsgError('Channel ID and Message ID are required')
      return
    }
    try {
      await addReactionRoleMessage(newChannelId.trim(), newMessageId.trim(), newLabel.trim())
      setNewChannelId('')
      setNewMessageId('')
      setNewLabel('')
      setShowAddMsg(false)
      load()
    } catch (err) {
      setAddMsgError(err.message)
    }
  }

  const handleDeleteMessage = async (messageId) => {
    if (!confirm('Delete this message and ALL its role mappings?')) return
    try {
      await deleteReactionRoleMessage(messageId)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleAddMapping = async (e) => {
    e.preventDefault()
    setAddMapError(null)
    if (!newEmoji.trim() || !newRoleId.trim()) {
      setAddMapError('Emoji and Role ID are required')
      return
    }
    try {
      await addReactionRoleMapping(
        addingTo,
        newEmoji.trim(),
        newRoleId.trim(),
        newRoleName.trim(),
        newEmojiId.trim() || undefined,
      )
      setNewEmoji('')
      setNewEmojiId('')
      setNewRoleId('')
      setNewRoleName('')
      setAddingTo(null)
      load()
    } catch (err) {
      setAddMapError(err.message)
    }
  }

  const handleDeleteMapping = async (mappingId) => {
    try {
      await deleteReactionRoleMapping(mappingId)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (loading) return <div className="flex justify-center py-8"><Spinner /></div>
  if (error) return <div className="text-sm text-accent-red">{error}</div>

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">
          {messages.length} tracked message{messages.length !== 1 ? 's' : ''}
        </p>
        <button
          onClick={() => setShowAddMsg(s => !s)}
          className="px-3 py-1.5 text-sm bg-secondary text-white rounded hover:bg-secondary/80 transition-colors"
        >
          {showAddMsg ? 'Cancel' : '+ Add Message'}
        </button>
      </div>

      {showAddMsg && (
        <form onSubmit={handleAddMessage} className="bg-bg-elevated border border-border rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-semibold text-text-primary">Track a New Message</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-text-muted mb-1">Channel ID</label>
              <input
                type="text"
                value={newChannelId}
                onChange={e => setNewChannelId(e.target.value)}
                placeholder="e.g. 1516071350463238185"
                className="w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Message ID</label>
              <input
                type="text"
                value={newMessageId}
                onChange={e => setNewMessageId(e.target.value)}
                placeholder="e.g. 1516072276955500666"
                className="w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Label (optional)</label>
              <input
                type="text"
                value={newLabel}
                onChange={e => setNewLabel(e.target.value)}
                placeholder="e.g. Role Assignment Part 1"
                className="w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none"
              />
            </div>
          </div>
          {addMsgError && <p className="text-xs text-accent-red">{addMsgError}</p>}
          <button
            type="submit"
            className="px-4 py-1.5 text-sm bg-secondary text-white rounded hover:bg-secondary/80 transition-colors"
          >
            Add Message
          </button>
        </form>
      )}

      {messages.length === 0 ? (
        <div className="text-sm text-text-muted py-4">No reaction role messages configured yet.</div>
      ) : (
        messages.map(msg => (
          <div key={msg.message_id} className="bg-bg-raised border border-border rounded-lg overflow-hidden">
            {/* Message header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-bg-elevated/50">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-text-primary">
                    {msg.label || 'Untitled Message'}
                  </span>
                  <span className="text-xs text-text-muted">
                    {msg.mappings?.length ?? 0} role{(msg.mappings?.length ?? 0) !== 1 ? 's' : ''}
                  </span>
                </div>
                <div className="flex gap-4 text-xs text-text-muted mt-0.5 font-mono">
                  <span>Channel: {msg.channel_id}</span>
                  <span>Message: {msg.message_id}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setAddingTo(addingTo === msg.message_id ? null : msg.message_id)
                    setAddMapError(null)
                    setNewEmoji('')
                    setNewEmojiId('')
                    setNewRoleId('')
                    setNewRoleName('')
                  }}
                  className="px-2 py-1 text-xs border border-border rounded hover:bg-bg-elevated transition-colors"
                >
                  {addingTo === msg.message_id ? 'Cancel' : '+ Add Role'}
                </button>
                <button
                  onClick={() => handleDeleteMessage(msg.message_id)}
                  className="px-2 py-1 text-xs text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/10 transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>

            {/* Add mapping form */}
            {addingTo === msg.message_id && (
              <form onSubmit={handleAddMapping} className="px-4 py-3 border-b border-border bg-bg-elevated/30 space-y-3">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs text-text-muted mb-1">Emoji</label>
                    <input
                      type="text"
                      value={newEmoji}
                      onChange={e => setNewEmoji(e.target.value)}
                      placeholder="Paste emoji or type name (e.g. volcano)"
                      className="w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-muted mb-1">Custom Emoji ID (optional)</label>
                    <input
                      type="text"
                      value={newEmojiId}
                      onChange={e => setNewEmojiId(e.target.value)}
                      placeholder="For custom Discord emojis"
                      className="w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-muted mb-1">Role ID</label>
                    <input
                      type="text"
                      value={newRoleId}
                      onChange={e => setNewRoleId(e.target.value)}
                      placeholder="Discord role ID"
                      className="w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-muted mb-1">Role Name (display only)</label>
                    <input
                      type="text"
                      value={newRoleName}
                      onChange={e => setNewRoleName(e.target.value)}
                      placeholder="e.g. Archimago Cabal"
                      className="w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none"
                    />
                  </div>
                </div>
                {addMapError && <p className="text-xs text-accent-red">{addMapError}</p>}
                <button
                  type="submit"
                  className="px-4 py-1.5 text-sm bg-secondary text-white rounded hover:bg-secondary/80 transition-colors"
                >
                  Add Mapping
                </button>
              </form>
            )}

            {/* Mappings table */}
            {msg.mappings?.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-text-muted border-b border-border">
                      <th className="px-4 py-2 font-medium">Emoji</th>
                      <th className="px-4 py-2 font-medium">Role Name</th>
                      <th className="px-4 py-2 font-medium">Role ID</th>
                      <th className="px-4 py-2 font-medium w-16"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {msg.mappings.map(m => (
                      <tr key={m.id} className="border-b border-border/50 last:border-b-0 hover:bg-bg-elevated/50">
                        <td className="px-4 py-2">
                          <span className="text-lg mr-2">{m.emoji}</span>
                          {m.emoji_id && <span className="text-xs text-text-muted font-mono">(custom: {m.emoji_id})</span>}
                        </td>
                        <td className="px-4 py-2 text-text-primary">{m.role_name || '-'}</td>
                        <td className="px-4 py-2 text-text-muted font-mono text-xs">{m.role_id}</td>
                        <td className="px-4 py-2 text-right">
                          <button
                            onClick={() => handleDeleteMapping(m.id)}
                            className="text-xs text-accent-red hover:underline"
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="px-4 py-4 text-sm text-text-muted">
                No role mappings yet. Click "+ Add Role" to add one.
              </div>
            )}
          </div>
        ))
      )}
    </section>
  )
}
