import { useState, useEffect } from 'react'

const COLUMNS = [
  { key: 'next_up', label: 'Next Up', color: 'border-yellow-500', description: 'The work you intend to tackle soon.' },
  { key: 'backlog', label: 'Backlog', color: 'border-purple-500', description: 'Worth keeping, but not scheduled.' },
  { key: 'resolved', label: 'Resolved', color: 'border-green-500', description: 'Shipped or otherwise completed.' },
  { key: 'not_planned', label: 'Not Planned', color: 'border-red-500', description: 'Closed without plans to start.' },
]

const TYPE_BADGES = {
  feature_request: { label: 'Feature', className: 'bg-blue-500/20 text-blue-400' },
  bug_report: { label: 'Bug', className: 'bg-red-500/20 text-red-400' },
  general: { label: 'General', className: 'bg-gray-500/20 text-gray-400' },
}

// What the "Feedback auto PR" GitHub Action did with an item.
const AUTO_BADGES = {
  pending: { label: 'Auto PR: waiting', className: 'bg-gray-500/20 text-gray-300' },
  claimed: { label: 'Auto PR: working', className: 'bg-yellow-500/20 text-yellow-300' },
  drafted: { label: 'Draft PR opened', className: 'bg-green-500/20 text-green-400' },
  duplicate: { label: 'Auto: duplicate', className: 'bg-purple-500/20 text-purple-300' },
  needs_human: { label: 'Auto: needs you', className: 'bg-orange-500/20 text-orange-300' },
  not_actionable: { label: 'Auto: no change', className: 'bg-gray-500/20 text-gray-400' },
  failed: { label: 'Auto PR failed', className: 'bg-red-500/20 text-red-400' },
}

// Items the Action isn't working on can be (re)sent to it.
const CAN_QUEUE = new Set([null, undefined, '', 'failed', 'needs_human', 'not_actionable', 'duplicate'])

function AutoPrRow({ item, onQueue }) {
  const badge = AUTO_BADGES[item.auto_status]
  const open = item.status === 'backlog' || item.status === 'next_up'
  if (!badge && !open) return null
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-1.5">
        {badge && (
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${badge.className}`}>
            {badge.label}
          </span>
        )}
        {item.auto_pr_url && (
          <a
            href={item.auto_pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-secondary hover:underline"
          >
            PR #{item.auto_pr_url.split('/').pop()} &#8599;
          </a>
        )}
        {open && CAN_QUEUE.has(item.auto_status) && (
          <button
            onClick={() => onQueue(item.id)}
            className="text-xs px-1.5 py-0.5 rounded bg-bg-surface border border-border text-text-muted hover:border-secondary hover:text-secondary transition-colors"
            title="Let the auto PR run look at this item"
          >
            {item.auto_status ? 'Try auto PR again' : 'Send to auto PR'}
          </button>
        )}
      </div>
      {item.auto_note && (
        <p className="text-xs text-text-muted/80 italic">{item.auto_note}</p>
      )}
    </div>
  )
}

function FeedbackCard({ item, onStatusChange, onDelete, onNotesChange, onQueue }) {
  const [editing, setEditing] = useState(false)
  const [notes, setNotes] = useState(item.admin_notes || '')
  const badge = TYPE_BADGES[item.type] || TYPE_BADGES.general

  const handleSaveNotes = () => {
    onNotesChange(item.id, notes)
    setEditing(false)
  }

  return (
    <div className="bg-bg-elevated border border-border rounded p-3 space-y-2 group">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1">
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${badge.className}`}>
            {badge.label}
          </span>
          {item.source === 'discord' && (
            <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-indigo-500/20 text-indigo-300">
              Discord
            </span>
          )}
        </div>
        <button
          onClick={() => onDelete(item.id)}
          className="text-text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity text-xs"
          title="Delete"
        >
          &times;
        </button>
      </div>
      <h4 className="text-sm font-semibold text-text-primary leading-tight">{item.title}</h4>
      <p className="text-xs text-text-muted line-clamp-3">{item.description}</p>
      {item.username && (
        <p className="text-xs text-text-muted">
          by <span className="text-primary">{item.username}</span>
        </p>
      )}
      <p className="text-xs text-text-muted/60">
        {new Date(item.created_at).toLocaleDateString()}
      </p>

      <AutoPrRow item={item} onQueue={onQueue} />

      {/* Admin notes */}
      {editing ? (
        <div className="space-y-1">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full bg-bg-surface border border-border rounded px-2 py-1 text-xs text-text-primary resize-none focus:outline-none focus:border-secondary"
            placeholder="Admin notes..."
          />
          <div className="flex gap-1 justify-end">
            <button onClick={() => setEditing(false)} className="text-xs text-text-muted hover:text-text">Cancel</button>
            <button onClick={handleSaveNotes} className="text-xs text-secondary hover:text-secondary/80">Save</button>
          </div>
        </div>
      ) : (
        <div
          onClick={() => setEditing(true)}
          className="text-xs text-text-muted/60 cursor-pointer hover:text-text-muted"
        >
          {item.admin_notes || '+ Add notes'}
        </div>
      )}

      {/* Status move buttons */}
      <div className="flex flex-wrap gap-1 pt-1 border-t border-border/50">
        {COLUMNS.filter((c) => c.key !== item.status).map((col) => (
          <button
            key={col.key}
            onClick={() => onStatusChange(item.id, col.key)}
            className="text-xs px-1.5 py-0.5 rounded bg-bg-surface border border-border text-text-muted hover:border-secondary hover:text-secondary transition-colors"
          >
            {col.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function FeedbackKanban() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchItems = async () => {
    try {
      const res = await fetch('/api/feedback/feedback', { credentials: 'include' })
      const data = await res.json()
      setItems(data.items || [])
    } catch {
      setError('Failed to load feedback')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchItems() }, [])

  const handleStatusChange = async (id, status) => {
    // Optimistic update
    setItems((prev) => prev.map((i) => i.id === id ? { ...i, status } : i))
    try {
      const res = await fetch(`/api/feedback/feedback/${id}/status`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      if (!res.ok) {
        fetchItems() // Revert on failure
      }
    } catch {
      fetchItems()
    }
  }

  const handleNotesChange = async (id, admin_notes) => {
    setItems((prev) => prev.map((i) => i.id === id ? { ...i, admin_notes } : i))
    try {
      const item = items.find((i) => i.id === id)
      await fetch(`/api/feedback/feedback/${id}/status`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: item?.status || 'backlog', admin_notes }),
      })
    } catch {
      fetchItems()
    }
  }

  const handleQueue = async (id) => {
    setItems((prev) => prev.map((i) => i.id === id ? { ...i, auto_status: 'pending', auto_note: null } : i))
    try {
      const res = await fetch(`/api/feedback/feedback/${id}/auto-queue`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) fetchItems()
    } catch {
      fetchItems()
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this feedback item?')) return
    setItems((prev) => prev.filter((i) => i.id !== id))
    try {
      await fetch(`/api/feedback/feedback/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
    } catch {
      fetchItems()
    }
  }

  if (loading) return <p className="text-text-muted text-sm">Loading feedback...</p>
  if (error) return <p className="text-red-400 text-sm">{error}</p>

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      {COLUMNS.map((col) => {
        const colItems = items.filter((i) => i.status === col.key)
        return (
          <div key={col.key} className={`border-t-2 ${col.color} bg-bg-surface rounded-lg`}>
            <div className="p-3 border-b border-border">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-text-primary text-sm">{col.label}</h3>
                <span className="text-xs bg-bg-elevated text-text-muted px-2 py-0.5 rounded-full font-medium">
                  {colItems.length}
                </span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">{col.description}</p>
            </div>
            <div className="p-2 space-y-2 max-h-[600px] overflow-y-auto">
              {colItems.length === 0 ? (
                <p className="text-xs text-text-muted/50 text-center py-4">No items</p>
              ) : (
                colItems.map((item) => (
                  <FeedbackCard
                    key={item.id}
                    item={item}
                    onStatusChange={handleStatusChange}
                    onDelete={handleDelete}
                    onNotesChange={handleNotesChange}
                    onQueue={handleQueue}
                  />
                ))
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
