import { useState, useEffect, useMemo, useRef } from 'react'
import { getCurioEntries, createCurioEntry, updateCurioEntry, deleteCurioEntry, createCurioSet } from '@/api/curios'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function CurioTracking() {
  usePageTitle('Curio Tracking')
  const [entries, setEntries] = useState([])
  const [sets, setSets] = useState([])
  const [canEdit, setCanEdit] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeSet, setActiveSet] = useState('all')
  const [modalOpen, setModalOpen] = useState(false)
  const [editingEntry, setEditingEntry] = useState(null)

  const fetchData = () => {
    getCurioEntries()
      .then((data) => {
        setEntries(data.entries || [])
        setSets(data.sets || [])
        setCanEdit(data.can_edit || false)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData() }, [])

  const filtered = useMemo(() => {
    if (activeSet === 'all') return entries
    return entries.filter((e) => String(e.set_id) === String(activeSet))
  }, [entries, activeSet])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Attribution Banner */}
      <div className="bg-bg-surface border border-border rounded-lg p-3 mb-6 text-center text-sm text-text-muted">
        Curio Tracking is a community effort done by{' '}
        <a href="https://www.youtube.com/@CardboardGuide" target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline">
          Cardboard Guide
        </a>{' '}
        and their{' '}
        <a href="https://discord.gg/6SBNc8FZ53" target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline">
          Discord
        </a>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        {/* Desktop pill buttons */}
        <div className="hidden sm:flex flex-wrap gap-2">
          <button
            onClick={() => setActiveSet('all')}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              activeSet === 'all' ? 'bg-secondary text-black' : 'bg-bg-raised text-text-muted hover:text-text-primary'
            }`}
          >
            All
          </button>
          {sets.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSet(String(s.id))}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                activeSet === String(s.id) ? 'bg-secondary text-black' : 'bg-bg-raised text-text-muted hover:text-text-primary'
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>

        {/* Mobile dropdown */}
        <select
          value={activeSet}
          onChange={(e) => setActiveSet(e.target.value)}
          className="sm:hidden bg-bg-raised border border-border rounded px-3 py-2 text-sm text-text-primary"
        >
          <option value="all">All Sets</option>
          {sets.map((s) => (
            <option key={s.id} value={String(s.id)}>{s.name}</option>
          ))}
        </select>

        {canEdit && (
          <button
            onClick={() => { setEditingEntry(null); setModalOpen(true) }}
            className="ml-auto bg-secondary hover:bg-secondary/80 text-black text-sm px-4 py-2 rounded transition-colors"
          >
            + Add Entry
          </button>
        )}
      </div>

      {/* Entry List */}
      {filtered.length > 0 ? (
        <div className="space-y-4">
          {filtered.map((entry) => (
            <EntryCard
              key={entry.id}
              entry={entry}
              canEdit={canEdit}
              onEdit={() => { setEditingEntry(entry); setModalOpen(true) }}
              onDelete={async () => {
                if (!confirm('Are you sure you want to delete this entry?')) return
                try {
                  await deleteCurioEntry(entry.id)
                  fetchData()
                } catch (err) {
                  alert(err.message || 'Failed to delete entry.')
                }
              }}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-text-muted">
          <p>No curio entries yet.</p>
          {canEdit && <p className="mt-1">Click "+ Add Entry" to create the first one.</p>}
        </div>
      )}

      {/* Modal */}
      {modalOpen && (
        <CurioModal
          entry={editingEntry}
          sets={sets}
          onClose={() => setModalOpen(false)}
          onSaved={() => { setModalOpen(false); fetchData() }}
        />
      )}
    </div>
  )
}

/* ---- Entry Card ---- */
function EntryCard({ entry, canEdit, onEdit, onDelete }) {
  return (
    <article className="bg-bg-surface border border-border rounded-lg overflow-hidden">
      <h2 className="text-lg font-display text-secondary px-4 pt-4 pb-2">{entry.name}</h2>
      <div className="flex flex-col sm:flex-row gap-4 px-4 pb-4">
        {entry.image_url && (
          <div className="sm:w-48 flex-shrink-0">
            <img
              src={entry.image_url}
              alt={entry.name}
              className="w-full rounded-lg object-cover"
              loading="lazy"
            />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="mb-2">
            <span className="text-xs text-text-muted">Number Pulled</span>
            <span className="block text-xl font-bold text-text-primary">{entry.number_pulled}</span>
          </div>
          <p className="text-sm text-text-muted mb-3">{entry.description}</p>
          <div className="flex items-center gap-3 text-xs text-text-muted">
            {entry.set_name && (
              <span className="bg-secondary/20 text-secondary px-2 py-0.5 rounded">{entry.set_name}</span>
            )}
            {entry.updated_at && (
              <span>Updated {entry.updated_at.slice(0, 10)}</span>
            )}
          </div>
          {canEdit && (
            <div className="flex gap-2 mt-3">
              <button onClick={onEdit} className="text-sm text-secondary hover:underline">Edit</button>
              <button onClick={onDelete} className="text-sm text-accent-red hover:underline">Delete</button>
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

/* ---- Modal ---- */
function CurioModal({ entry, sets, onClose, onSaved }) {
  const isEdit = !!entry
  const [name, setName] = useState(entry?.name || '')
  const [numberPulled, setNumberPulled] = useState(entry?.number_pulled ?? '')
  const [description, setDescription] = useState(entry?.description || '')
  const [setId, setSetId] = useState(entry?.set_id ? String(entry.set_id) : '')
  const [customSetName, setCustomSetName] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(entry?.image_url || '')
  const [saving, setSaving] = useState(false)
  const fileRef = useRef(null)

  const handleImageChange = (e) => {
    const file = e.target.files[0]
    if (file) {
      setImageFile(file)
      setPreviewUrl(URL.createObjectURL(file))
    }
  }

  const handleSubmit = async () => {
    if (!name.trim()) return alert('Curio name is required.')
    if (numberPulled === '' || Number(numberPulled) < 0) return alert('Number pulled must be a non-negative number.')
    if (!description.trim()) return alert('Description is required.')
    if (!isEdit && !imageFile) return alert('An image is required for new entries.')

    setSaving(true)
    try {
      let resolvedSetId = setId

      if (setId === 'other') {
        if (!customSetName.trim()) {
          setSaving(false)
          return alert('Please enter a custom set name.')
        }
        const newSet = await createCurioSet(customSetName.trim())
        resolvedSetId = String(newSet.id)
      }

      const formData = new FormData()
      formData.append('name', name.trim())
      formData.append('number_pulled', numberPulled)
      formData.append('description', description.trim())
      formData.append('set_id', resolvedSetId)
      if (imageFile) formData.append('image', imageFile)

      if (isEdit) {
        await updateCurioEntry(entry.id, formData)
      } else {
        await createCurioEntry(formData)
      }
      onSaved()
    } catch (err) {
      alert(err.message || 'Failed to save entry.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div
        className="relative bg-bg-surface border border-border rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="font-display text-secondary text-lg">{isEdit ? 'Edit Entry' : 'Add Entry'}</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xl leading-none">&times;</button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-sm text-text-muted mb-1">Curio Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
              placeholder="Name of the curio"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-text-muted mb-1">Number Pulled</label>
            <input
              type="number"
              value={numberPulled}
              onChange={(e) => setNumberPulled(e.target.value)}
              min={0}
              placeholder="0"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-text-muted mb-1">Short Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              rows={3}
              placeholder="Brief description of the curio"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm resize-none"
            />
          </div>

          <div>
            <label className="block text-sm text-text-muted mb-1">Set</label>
            <select
              value={setId}
              onChange={(e) => setSetId(e.target.value)}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
            >
              <option value="" disabled>Select a set</option>
              {sets.map((s) => (
                <option key={s.id} value={String(s.id)}>{s.name}</option>
              ))}
              <option value="other">Other</option>
            </select>
          </div>

          {setId === 'other' && (
            <div>
              <label className="block text-sm text-text-muted mb-1">Custom Set Name</label>
              <input
                type="text"
                value={customSetName}
                onChange={(e) => setCustomSetName(e.target.value)}
                maxLength={100}
                placeholder="Enter new set name"
                className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
              />
            </div>
          )}

          <div>
            <label className="block text-sm text-text-muted mb-1">Picture</label>
            <input
              ref={fileRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.gif"
              onChange={handleImageChange}
              className="w-full text-sm text-text-muted file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:bg-bg-raised file:text-text-primary"
            />
            {previewUrl && (
              <img src={previewUrl} alt="Preview" className="mt-2 max-h-40 rounded-lg object-cover" />
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-5 py-4 border-t border-border">
          <button onClick={onClose} className="text-sm text-text-muted hover:text-text-primary px-4 py-2">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="bg-secondary hover:bg-secondary/80 text-black text-sm px-4 py-2 rounded transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Entry'}
          </button>
        </div>
      </div>
    </div>
  )
}
