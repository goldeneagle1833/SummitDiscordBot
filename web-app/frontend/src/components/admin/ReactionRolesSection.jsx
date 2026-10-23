import { useState, useEffect, useCallback } from 'react'
import {
  getReactionRoleMessages,
  addReactionRoleMessage,
  deleteReactionRoleMessage,
  addReactionRoleMapping,
  deleteReactionRoleMapping,
  updateReactionRoleMessage,
  createReactionRolePost,
  deleteReactionRolePost,
} from '@/api/admin'
import Spinner from '@/components/ui/Spinner'

// Discord allows 20 different reactions on one message.
const MAX_ROLES = 20

const inputClass = 'w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none'

export default function ReactionRolesSection() {
  const [messages, setMessages] = useState([])
  const [posts, setPosts] = useState([])
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

  // New bot post form
  const [showPost, setShowPost] = useState(false)
  const [postChannelId, setPostChannelId] = useState('')
  const [postTitle, setPostTitle] = useState('')
  const [postBody, setPostBody] = useState('')
  const [postError, setPostError] = useState(null)

  // Edit text of a bot-posted message
  const [editing, setEditing] = useState(null) // message_id being edited
  const [editTitle, setEditTitle] = useState('')
  const [editBody, setEditBody] = useState('')
  const [editError, setEditError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getReactionRoleMessages()
      .then(d => {
        setMessages(d.messages ?? [])
        setPosts(d.posts ?? [])
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  // While a post is waiting on the bot, refresh quietly until it lands.
  const hasPending = posts.some(p => p.status === 'pending')
  useEffect(() => {
    if (!hasPending) return
    const t = setTimeout(() => {
      getReactionRoleMessages()
        .then(d => {
          setMessages(d.messages ?? [])
          setPosts(d.posts ?? [])
        })
        .catch(() => {})
    }, 4000)
    return () => clearTimeout(t)
  }, [hasPending, posts])

  const handleCreatePost = async (e) => {
    e.preventDefault()
    setPostError(null)
    if (!postChannelId.trim() || !postTitle.trim()) {
      setPostError('Channel ID and Title are required')
      return
    }
    try {
      await createReactionRolePost(postChannelId.trim(), postTitle.trim(), postBody.trim())
      setPostChannelId('')
      setPostTitle('')
      setPostBody('')
      setShowPost(false)
      load()
    } catch (err) {
      setPostError(err.message)
    }
  }

  const handleDismissPost = async (postId) => {
    try {
      await deleteReactionRolePost(postId)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const startEdit = (msg) => {
    setEditing(msg.message_id)
    setEditTitle(msg.title || msg.label || '')
    setEditBody(msg.body || '')
    setEditError(null)
  }

  const handleSaveEdit = async (e) => {
    e.preventDefault()
    setEditError(null)
    if (!editTitle.trim()) {
      setEditError('Title is required')
      return
    }
    try {
      await updateReactionRoleMessage(editing, editTitle.trim(), editBody.trim())
      setEditing(null)
      load()
    } catch (err) {
      setEditError(err.message)
    }
  }

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

  const handleDeleteMessage = async (msg) => {
    const messageId = msg.message_id
    const prompt = msg.managed
      ? 'Delete this message from Discord and remove ALL its role mappings? Members keep roles they already have.'
      : 'Stop tracking this message and remove ALL its role mappings? The Discord message itself stays.'
    if (!confirm(prompt)) return
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
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-text-muted">
          {messages.length} tracked message{messages.length !== 1 ? 's' : ''}
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => { setShowPost(s => !s); setShowAddMsg(false) }}
            className="px-3 py-1.5 text-sm bg-secondary text-white rounded hover:bg-secondary/80 transition-colors"
          >
            {showPost ? 'Cancel' : '+ Post New Message'}
          </button>
          <button
            onClick={() => { setShowAddMsg(s => !s); setShowPost(false) }}
            className="px-3 py-1.5 text-sm border border-border rounded hover:bg-bg-elevated transition-colors"
          >
            {showAddMsg ? 'Cancel' : 'Track Existing Message'}
          </button>
        </div>
      </div>

      <p className="text-xs text-text-muted">
        Changes reach Discord within a few seconds, no restart needed. The bot adds each emoji to the
        message and gives the role to anyone who already reacted.
      </p>

      {showPost && (
        <form onSubmit={handleCreatePost} className="bg-bg-elevated border border-border rounded-lg p-4 space-y-3">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">Post a New Role Message</h3>
            <p className="text-xs text-text-muted mt-0.5">
              The bot posts this in the channel. Add roles to it afterwards and the bot keeps the role list on the post up to date.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-text-muted mb-1">Channel ID</label>
              <input
                type="text"
                value={postChannelId}
                onChange={e => setPostChannelId(e.target.value)}
                placeholder="e.g. 1516071350463238185"
                className={inputClass}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-text-muted mb-1">Title</label>
              <input
                type="text"
                value={postTitle}
                onChange={e => setPostTitle(e.target.value)}
                maxLength={256}
                placeholder="e.g. Pick Your Avatar Clubs"
                className={inputClass}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Text (optional)</label>
            <textarea
              value={postBody}
              onChange={e => setPostBody(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="React below to join a club. Remove your reaction to leave."
              className={inputClass}
            />
          </div>
          {postError && <p className="text-xs text-accent-red">{postError}</p>}
          <button
            type="submit"
            className="px-4 py-1.5 text-sm bg-secondary text-white rounded hover:bg-secondary/80 transition-colors"
          >
            Post to Discord
          </button>
        </form>
      )}

      {posts.map(p => (
        <div
          key={p.id}
          className={`flex flex-wrap items-center justify-between gap-2 px-4 py-3 rounded-lg border text-sm ${
            p.status === 'failed' ? 'border-accent-red/30 bg-accent-red/10' : 'border-border bg-bg-elevated'
          }`}
        >
          <div className="min-w-0">
            <span className="font-semibold text-text-primary">{p.title}</span>
            <span className="text-xs text-text-muted ml-2 font-mono">Channel: {p.channel_id}</span>
            {p.status === 'failed'
              ? <p className="text-xs text-accent-red mt-0.5">Not posted: {p.error}</p>
              : <div className="text-xs text-text-muted mt-0.5 flex items-center gap-2"><Spinner size="sm" /> Waiting for the bot to post…</div>}
          </div>
          <button
            onClick={() => handleDismissPost(p.id)}
            className="px-2 py-1 text-xs border border-border rounded hover:bg-bg-raised transition-colors"
          >
            {p.status === 'failed' ? 'Dismiss' : 'Cancel'}
          </button>
        </div>
      ))}

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
            <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-border bg-bg-elevated/50">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-text-primary">
                    {msg.label || 'Untitled Message'}
                  </span>
                  <span className="text-xs text-text-muted">
                    {msg.mappings?.length ?? 0} / {MAX_ROLES} roles
                  </span>
                  {msg.managed ? (
                    <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-secondary/15 text-secondary">
                      Posted by bot
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-x-4 text-xs text-text-muted mt-0.5 font-mono">
                  <span>Channel: {msg.channel_id}</span>
                  <span>Message: {msg.message_id}</span>
                </div>
              </div>
              <div className="flex gap-2">
                {msg.managed ? (
                  <button
                    onClick={() => (editing === msg.message_id ? setEditing(null) : startEdit(msg))}
                    className="px-2 py-1 text-xs border border-border rounded hover:bg-bg-elevated transition-colors"
                  >
                    {editing === msg.message_id ? 'Cancel' : 'Edit Text'}
                  </button>
                ) : null}
                <button
                  disabled={(msg.mappings?.length ?? 0) >= MAX_ROLES && addingTo !== msg.message_id}
                  title={(msg.mappings?.length ?? 0) >= MAX_ROLES ? 'Discord allows 20 reactions per message' : undefined}
                  onClick={() => {
                    setAddingTo(addingTo === msg.message_id ? null : msg.message_id)
                    setAddMapError(null)
                    setNewEmoji('')
                    setNewEmojiId('')
                    setNewRoleId('')
                    setNewRoleName('')
                  }}
                  className="px-2 py-1 text-xs border border-border rounded hover:bg-bg-elevated transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {addingTo === msg.message_id ? 'Cancel' : '+ Add Role'}
                </button>
                <button
                  onClick={() => handleDeleteMessage(msg)}
                  className="px-2 py-1 text-xs text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/10 transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>

            {/* Edit text of a bot-posted message */}
            {editing === msg.message_id && (
              <form onSubmit={handleSaveEdit} className="px-4 py-3 border-b border-border bg-bg-elevated/30 space-y-3">
                <div>
                  <label className="block text-xs text-text-muted mb-1">Title</label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    maxLength={256}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-muted mb-1">Text</label>
                  <textarea
                    value={editBody}
                    onChange={e => setEditBody(e.target.value)}
                    maxLength={2000}
                    rows={3}
                    className={inputClass}
                  />
                </div>
                {editError && <p className="text-xs text-accent-red">{editError}</p>}
                <button
                  type="submit"
                  className="px-4 py-1.5 text-sm bg-secondary text-white rounded hover:bg-secondary/80 transition-colors"
                >
                  Save and Update Discord
                </button>
              </form>
            )}

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
