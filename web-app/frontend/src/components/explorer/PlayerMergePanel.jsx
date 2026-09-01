import { useState, useEffect } from 'react'
import {
  fetchPotentialDuplicates,
  fetchAliases,
  fetchAllPlayers,
  mergePlayers,
  deleteAlias,
} from '@/api/explorer'

function DuplicateGroup({ group, onMerge }) {
  const [canonical, setCanonical] = useState(null)
  const [alias, setAlias] = useState(null)
  const [merging, setMerging] = useState(false)

  const handleMerge = async () => {
    if (!canonical || !alias || canonical === alias) return
    setMerging(true)
    try {
      const canonPlayer = group.players.find((p) => p.cardeio_user_id === canonical)
      const aliasPlayer = group.players.find((p) => p.cardeio_user_id === alias)
      await onMerge(alias, canonical, aliasPlayer?.display_name, canonPlayer?.display_name)
      setCanonical(null)
      setAlias(null)
    } finally {
      setMerging(false)
    }
  }

  return (
    <div className="bg-bg-elevated rounded-lg p-3 space-y-2">
      <p className="text-xs text-text-muted">
        Matched name: <span className="text-text-primary font-medium">{group.normalized_name}</span>
      </p>
      <div className="space-y-1">
        {group.players.map((p) => (
          <div key={p.cardeio_user_id} className="flex items-center gap-2 text-sm">
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="radio"
                name={`canonical-${group.normalized_name}`}
                checked={canonical === p.cardeio_user_id}
                onChange={() => { setCanonical(p.cardeio_user_id); if (alias === p.cardeio_user_id) setAlias(null) }}
                className="accent-green-500"
              />
              <span className="text-green-400 text-xs">Keep</span>
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="radio"
                name={`alias-${group.normalized_name}`}
                checked={alias === p.cardeio_user_id}
                onChange={() => { setAlias(p.cardeio_user_id); if (canonical === p.cardeio_user_id) setCanonical(null) }}
                className="accent-red-500"
              />
              <span className="text-red-400 text-xs">Merge</span>
            </label>
            <span className="text-text-primary">{p.display_name}</span>
            <span className="text-text-muted text-xs">({p.event_count} event{p.event_count !== 1 ? 's' : ''})</span>
          </div>
        ))}
      </div>
      <button
        onClick={handleMerge}
        disabled={!canonical || !alias || canonical === alias || merging}
        className="px-3 py-1 text-xs bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-40"
      >
        {merging ? 'Merging...' : 'Merge Selected'}
      </button>
    </div>
  )
}

function ManualMerge({ players, onMerge }) {
  const [canonical, setCanonical] = useState('')
  const [alias, setAlias] = useState('')
  const [merging, setMerging] = useState(false)

  const handleMerge = async () => {
    if (!canonical || !alias || canonical === alias) return
    setMerging(true)
    try {
      const canonPlayer = players.find((p) => p.cardeio_user_id === canonical)
      const aliasPlayer = players.find((p) => p.cardeio_user_id === alias)
      await onMerge(alias, canonical, aliasPlayer?.display_name, canonPlayer?.display_name)
      setCanonical('')
      setAlias('')
    } finally {
      setMerging(false)
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted font-medium uppercase tracking-wide">Manual Merge</p>
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex-1">
          <label className="text-xs text-green-400 block mb-1">Keep (Primary)</label>
          <select
            value={canonical}
            onChange={(e) => setCanonical(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm"
          >
            <option value="">Select player...</option>
            {players.map((p) => (
              <option key={p.cardeio_user_id} value={p.cardeio_user_id} disabled={p.cardeio_user_id === alias}>
                {p.display_name} ({p.event_count} events)
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-red-400 block mb-1">Merge Into (Duplicate)</label>
          <select
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded px-3 py-1.5 text-sm"
          >
            <option value="">Select player...</option>
            {players.map((p) => (
              <option key={p.cardeio_user_id} value={p.cardeio_user_id} disabled={p.cardeio_user_id === canonical}>
                {p.display_name} ({p.event_count} events)
              </option>
            ))}
          </select>
        </div>
      </div>
      <button
        onClick={handleMerge}
        disabled={!canonical || !alias || canonical === alias || merging}
        className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors disabled:opacity-40"
      >
        {merging ? 'Merging...' : 'Merge Players'}
      </button>
    </div>
  )
}

export default function PlayerMergePanel() {
  const [duplicates, setDuplicates] = useState([])
  const [aliases, setAliases] = useState([])
  const [players, setPlayers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [dups, als, pls] = await Promise.all([
        fetchPotentialDuplicates(),
        fetchAliases(),
        fetchAllPlayers(),
      ])
      setDuplicates(dups)
      setAliases(als)
      setPlayers(pls)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleMerge = async (aliasUserId, canonicalUserId, aliasName, canonicalName) => {
    try {
      await mergePlayers(aliasUserId, canonicalUserId, aliasName, canonicalName)
      load()
    } catch (e) {
      alert(`Merge failed: ${e.message}`)
    }
  }

  const handleDeleteAlias = async (aliasId) => {
    if (!confirm('Unlink this player alias?')) return
    try {
      await deleteAlias(aliasId)
      load()
    } catch (e) {
      alert(`Failed to remove alias: ${e.message}`)
    }
  }

  if (loading) return <p className="text-sm text-text-muted">Loading player data...</p>

  return (
    <div className="space-y-5">
      {error && <p className="text-xs text-red-400">{error}</p>}

      {/* Detected duplicates */}
      {duplicates.length > 0 && (
        <div>
          <p className="text-xs text-text-muted font-medium uppercase tracking-wide mb-2">
            Detected Duplicates ({duplicates.length} group{duplicates.length !== 1 ? 's' : ''})
          </p>
          <div className="space-y-2">
            {duplicates.map((group) => (
              <DuplicateGroup key={group.normalized_name} group={group} onMerge={handleMerge} />
            ))}
          </div>
        </div>
      )}

      {duplicates.length === 0 && (
        <p className="text-sm text-text-muted">No duplicate players detected by name matching.</p>
      )}

      {/* Manual merge */}
      {players.length > 1 && <ManualMerge players={players} onMerge={handleMerge} />}

      {/* Existing aliases */}
      {aliases.length > 0 && (
        <div>
          <p className="text-xs text-text-muted font-medium uppercase tracking-wide mb-2">
            Active Aliases ({aliases.length})
          </p>
          <div className="space-y-1">
            {aliases.map((a) => (
              <div key={a.id} className="flex items-center justify-between py-1.5 border-b border-border/40 text-sm">
                <div>
                  <span className="text-red-400">{a.alias_display_name || a.alias_user_id}</span>
                  <span className="text-text-muted mx-2">&rarr;</span>
                  <span className="text-green-400">{a.canonical_display_name || a.canonical_user_id}</span>
                </div>
                <button
                  onClick={() => handleDeleteAlias(a.id)}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors px-2 py-0.5"
                >
                  Unlink
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
