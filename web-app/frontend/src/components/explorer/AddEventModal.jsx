import { useState, useEffect } from 'react'
import { previewEvent, saveEvent } from '@/api/explorer'

export default function AddEventModal({ seasons, onClose, onSaved }) {
  const [url, setUrl] = useState('')
  const [seasonId, setSeasonId] = useState(seasons[0]?.id ?? '')
  const [step, setStep] = useState('input') // 'input' | 'preview'
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') { if (step === 'preview') { setStep('input'); setError(null) } else onClose() } }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, step])

  const handlePreview = async (e) => {
    e.preventDefault()
    if (!url.trim() || !seasonId) return
    setLoading(true)
    setError(null)
    try {
      const data = await previewEvent(url.trim(), seasonId)
      setPreview(data)
      setStep('preview')
    } catch (err) {
      if (err.status === 400) setError('Invalid URL. Must be a sorcerytcg.com event URL.')
      else if (err.status === 409) setError('This event has already been imported.')
      else if (err.status === 502) setError('Could not reach carde.io. The event may not be published yet.')
      else setError(err.message || 'Failed to fetch event')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await saveEvent(url.trim(), seasonId)
      onSaved()
    } catch (err) {
      if (err.status === 409) setError('This event has already been imported.')
      else setError(err.message || 'Failed to save event')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-lg mx-4 max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="p-5 border-b border-border flex-shrink-0">
          <h3 className="text-lg font-semibold text-text-primary">
            {step === 'input' ? 'Import Event' : 'Confirm Import'}
          </h3>
        </div>

        <div className="p-5 overflow-y-auto flex-1">
          {step === 'input' ? (
            <form onSubmit={handlePreview} className="space-y-3">
              <div>
                <label className="text-xs text-text-muted block mb-1">Event URL *</label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://play.sorcerytcg.com/events/..."
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Season *</label>
                <select
                  value={seasonId}
                  onChange={(e) => setSeasonId(e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                  required
                >
                  {seasons.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary transition-colors">
                  Cancel
                </button>
                <button type="submit" disabled={loading || !url.trim()} className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-40">
                  {loading ? 'Fetching...' : 'Preview'}
                </button>
              </div>
            </form>
          ) : (
            <div className="space-y-4">
              {/* Event summary */}
              <div className="bg-bg-elevated rounded-lg p-3 text-sm space-y-1">
                <div className="flex justify-between">
                  <span className="text-text-muted">Event</span>
                  <span className="text-text-primary font-medium">{preview.event_name}</span>
                </div>
                {preview.event_date && (
                  <div className="flex justify-between">
                    <span className="text-text-muted">Date</span>
                    <span className="text-text-primary">{preview.event_date}</span>
                  </div>
                )}
                {preview.venue_name && (
                  <div className="flex justify-between">
                    <span className="text-text-muted">Venue</span>
                    <span className="text-text-primary">{preview.venue_name}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-text-muted">Players</span>
                  <span className="text-text-primary">{preview.total_players}</span>
                </div>
                {preview.top_cut_size > 0 && (
                  <div className="flex justify-between">
                    <span className="text-text-muted">Top Cut</span>
                    <span className="text-text-primary">Top {preview.top_cut_size}</span>
                  </div>
                )}
              </div>

              {/* Standings table */}
              <div>
                <p className="text-xs text-text-muted font-medium uppercase tracking-wide mb-2">Standings Preview</p>
                <div className="overflow-x-auto max-h-64">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-bg-surface">
                      <tr className="border-b border-border text-left">
                        <th className="py-1.5 px-2 text-text-muted w-10">#</th>
                        <th className="py-1.5 px-2 text-text-muted">Player</th>
                        <th className="py-1.5 px-2 text-text-muted text-right">Wins</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(preview.results || []).map((r) => (
                        <tr key={r.cardeio_user_id} className="border-b border-border/40">
                          <td className="py-1 px-2 text-text-muted">{r.final_standing}</td>
                          <td className="py-1 px-2 text-text-primary">{r.display_name}</td>
                          <td className="py-1 px-2 text-text-muted text-right">{r.wins}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {error && <p className="text-xs text-red-400">{error}</p>}

              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => { setStep('input'); setError(null) }}
                  className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-40"
                >
                  {saving ? 'Importing...' : 'Confirm Import'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
