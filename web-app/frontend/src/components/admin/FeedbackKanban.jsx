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

function FeedbackCard({ item, onStatusChange, onDelete, onNotesChange }) {
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
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${badge.className}`}>
          {badge.label}
        </span>
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
