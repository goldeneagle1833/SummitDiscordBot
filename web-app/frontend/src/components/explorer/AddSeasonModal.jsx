import { useState, useEffect } from 'react'
import { createSeason } from '@/api/explorer'

const RULE_SETS = {
  explorer: {
    label: 'Explorer Rules',
    description: 'Participation + win bonus (Pathfinder) and top-cut placement (Persecutor). Qualify at Persecutor ≥ 10.',
    config: {
      participation: 10,
      bonus_pathfinder: { '0': 5, '1': 4, '2': 3 },
      persecutor: { '1': 10, '2': 5, '3': 4, '4': 4, '5': 3, '6': 3, '7': 2, '8': 2 },
      trials_threshold: 10,
    },
  },
  flat: {
    label: 'Flat Points',
    description: 'Fixed participation points only — no win bonus or top-cut points.',
    config: {
      participation: 10,
      bonus_pathfinder: {},
      persecutor: {},
      trials_threshold: 0,
    },
  },
  custom: {
    label: 'Custom',
    description: 'Define your own points configuration as JSON.',
    config: null,
  },
}

export default function AddSeasonModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [ruleSet, setRuleSet] = useState('explorer')
  const [customJson, setCustomJson] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return

    let pointsConfig = RULE_SETS[ruleSet].config
    if (ruleSet === 'custom') {
      try {
        pointsConfig = JSON.parse(customJson)
      } catch {
        setError('Invalid JSON for custom rule set')
        return
      }
    }

    setSaving(true)
    setError(null)
    try {
      const result = await createSeason(name.trim(), description.trim() || null, pointsConfig)
      onCreated(result.season)
    } catch (err) {
      if (err.status === 409) {
        setError('Series already exists')
      } else {
        setError(err.message || 'Failed to create series')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="p-5">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Add Series</h3>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-text-muted block mb-1">Series Name *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Community Series 3"
                className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="text-xs text-text-muted block mb-1">Description (optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
                rows={2}
                className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm resize-none"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted block mb-1">Rule Set *</label>
              <select
                value={ruleSet}
                onChange={(e) => setRuleSet(e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
              >
                {Object.entries(RULE_SETS).map(([key, { label }]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
              <p className="text-xs text-text-muted mt-1">{RULE_SETS[ruleSet].description}</p>
            </div>
            {ruleSet === 'custom' && (
              <div>
                <label className="text-xs text-text-muted block mb-1">Points Config (JSON) *</label>
                <textarea
                  value={customJson}
                  onChange={(e) => setCustomJson(e.target.value)}
                  placeholder={'{\n  "participation": 10,\n  "bonus_pathfinder": {"0": 5},\n  "persecutor": {"1": 10},\n  "trials_threshold": 10\n}'}
                  rows={5}
                  className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm font-mono resize-none"
                />
              </div>
            )}
            {error && <p className="text-xs text-red-400">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving || !name.trim()}
                className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-40"
              >
                {saving ? 'Creating...' : 'Create Series'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
