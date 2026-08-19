import { useEffect, useState } from 'react'
import { correctMatchAvatars, removePlayer, removeMatch, resetElo, renamePlayer, deleteAccount } from '@/api/admin'
import { get } from '@/api/client'
import { listAllAvatars } from '@/api/games'

export default function AdminControls({ playerId, playerName, onAction }) {
  const [modal, setModal] = useState(null)
  const [matchId, setMatchId] = useState('')
  const [winnerAvatar, setWinnerAvatar] = useState('')
  const [loserAvatar, setLoserAvatar] = useState('')
  const [eloValue, setEloValue] = useState('1500')
  const [eloSource, setEloSource] = useState('both')
  const [eloAvatar, setEloAvatar] = useState('')
  const [avatarSpecificEvent, setAvatarSpecificEvent] = useState(false)
  const [avatars, setAvatars] = useState([])
  const [newName, setNewName] = useState(playerName || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([get('/api/events'), listAllAvatars()])
      .then(([eventData, avatarList]) => {
        setAvatarSpecificEvent(Boolean(eventData.active_event?.avatar_specific))
        setAvatars(avatarList || [])
      })
      .catch(() => {})
  }, [])

  const close = () => { setModal(null); setError(null) }

  const doAction = async (fn) => {
    setSaving(true); setError(null)
    try {
      await fn()
      close()
      onAction?.()
    } catch (err) {
      setError(err.message || 'Action failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemovePlayer = () => {
    if (!confirm(`Remove player "${playerName}" from the leaderboard? This cannot be undone.`)) return
    doAction(() => removePlayer(playerId))
  }

  const handleDeleteAccount = () => {
    if (!confirm(`DELETE ACCOUNT for "${playerName}"? This will permanently remove ALL data (ELO, matches, profile, etc). This cannot be undone.`)) return
    if (!confirm(`Are you absolutely sure? Type the player name to confirm.\n\nThis will delete: "${playerName}"`)) return
    doAction(() => deleteAccount(playerId))
  }

  const handleRemoveMatch = () => {
    if (!matchId.trim()) { setError('Enter a match ID.'); return }
    doAction(() => removeMatch(matchId.trim()))
  }

  const handleResetElo = () => {
    const elo = parseInt(eloValue)
    if (isNaN(elo) || elo < 0 || elo > 5000) { setError('ELO must be 0-5000.'); return }
    if (avatarSpecificEvent && !eloAvatar) { setError('Select an avatar for the active event.'); return }
    doAction(() => resetElo(playerId, elo, eloSource, eloAvatar))
  }

  const handleCorrectMatchAvatars = () => {
    if (!matchId.trim()) { setError('Enter a match ID.'); return }
    if (!winnerAvatar || !loserAvatar) { setError('Select both avatars.'); return }
    doAction(() => correctMatchAvatars(matchId.trim(), winnerAvatar, loserAvatar))
  }

  const handleRename = () => {
    const trimmed = newName.trim()
    if (!trimmed || trimmed.length > 100) { setError('Name must be 1-100 characters.'); return }
    doAction(() => renamePlayer(playerId, trimmed))
  }

  return (
    <>
      <div className="rounded-lg p-4 mb-4" style={{ background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.3)' }}>
        <h3 className="text-sm font-semibold text-accent-red mb-3">Admin Controls</h3>
        <div className="flex flex-wrap gap-2">
          <button onClick={handleRemovePlayer} className="px-3 py-1.5 text-xs bg-accent-red/20 text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/30">
            Remove Player
          </button>
          <button onClick={() => { setMatchId(''); setModal('removeMatch') }} className="px-3 py-1.5 text-xs bg-accent-red/20 text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/30">
            Remove Match
          </button>
          {avatarSpecificEvent && (
            <button onClick={() => { setMatchId(''); setWinnerAvatar(''); setLoserAvatar(''); setModal('correctAvatars') }} className="px-3 py-1.5 text-xs bg-bg-raised border border-border rounded text-text-muted hover:text-text-primary">
              Correct Match Avatars
            </button>
          )}
          <button onClick={() => { setEloValue('1500'); setEloSource('both'); setEloAvatar(''); setModal('resetElo') }} className="px-3 py-1.5 text-xs bg-bg-raised border border-border rounded text-text-muted hover:text-text-primary">
            Set ELO
          </button>
          <button onClick={() => { setNewName(playerName || ''); setModal('rename') }} className="px-3 py-1.5 text-xs bg-bg-raised border border-border rounded text-text-muted hover:text-text-primary">
            Rename Player
          </button>
          <button onClick={handleDeleteAccount} className="px-3 py-1.5 text-xs bg-accent-red/20 text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/30">
            Delete Account
          </button>
        </div>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={close}>
          <div className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            {modal === 'removeMatch' && (
              <>
                <h3 className="text-lg font-semibold text-text-primary mb-4">Remove Match</h3>
                <input
                  type="text"
                  value={matchId}
                  onChange={(e) => setMatchId(e.target.value)}
                  placeholder="Match ID"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-2"
                  autoFocus
                />
                <p className="text-xs text-text-muted mb-4">This will reverse ELO changes from this match.</p>
              </>
            )}
            {modal === 'resetElo' && (
              <>
                <h3 className="text-lg font-semibold text-text-primary mb-4">Set ELO</h3>
                <input
                  type="number"
                  value={eloValue}
                  onChange={(e) => setEloValue(e.target.value)}
                  min={0} max={5000}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3"
                  autoFocus
                />
                <label className="text-xs text-text-muted block mb-1">Source</label>
                <select
                  value={eloSource}
                  onChange={(e) => setEloSource(e.target.value)}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
                >
                  <option value="both">Both</option>
                  <option value="bot">Online (Bot)</option>
                  <option value="paper">Paper (Web)</option>
                </select>
                {avatarSpecificEvent && (
                  <>
                    <label className="text-xs text-text-muted block mb-1">Avatar *</label>
                    <select
                      value={eloAvatar}
                      onChange={(e) => setEloAvatar(e.target.value)}
                      className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-2"
                    >
                      <option value="">Select avatar...</option>
                      {avatars.map((avatar) => <option key={avatar} value={avatar}>{avatar}</option>)}
                    </select>
                    <p className="text-xs text-text-muted mb-4">
                      The lifetime rating and this avatar's active-event rating will be set.
                    </p>
                  </>
                )}
              </>
            )}
            {modal === 'correctAvatars' && (
              <>
                <h3 className="text-lg font-semibold text-text-primary mb-4">Correct Match Avatars</h3>
                <input
                  type="text"
                  value={matchId}
                  onChange={(e) => setMatchId(e.target.value)}
                  placeholder="Match ID (for example 42 or web_42)"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3"
                  autoFocus
                />
                <label className="text-xs text-text-muted block mb-1">Winner avatar</label>
                <select value={winnerAvatar} onChange={(e) => setWinnerAvatar(e.target.value)} className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3">
                  <option value="">Select avatar...</option>
                  {avatars.map((avatar) => <option key={avatar} value={avatar}>{avatar}</option>)}
                </select>
                <label className="text-xs text-text-muted block mb-1">Loser avatar</label>
                <select value={loserAvatar} onChange={(e) => setLoserAvatar(e.target.value)} className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-2">
                  <option value="">Select avatar...</option>
                  {avatars.map((avatar) => <option key={avatar} value={avatar}>{avatar}</option>)}
                </select>
                <p className="text-xs text-text-muted mb-4">Lifetime ELO stays unchanged; the avatar ladder is replayed.</p>
              </>
            )}
            {modal === 'rename' && (
              <>
                <h3 className="text-lg font-semibold text-text-primary mb-4">Rename Player</h3>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="New player name"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4"
                  autoFocus
                />
              </>
            )}
            {error && <p className="text-xs text-accent-red mb-3">{error}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={close} className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary">Cancel</button>
              <button
                onClick={modal === 'removeMatch' ? handleRemoveMatch : modal === 'correctAvatars' ? handleCorrectMatchAvatars : modal === 'resetElo' ? handleResetElo : handleRename}
                disabled={saving}
                className={`px-3 py-1.5 text-sm rounded hover:opacity-90 disabled:opacity-40 ${
                  modal === 'removeMatch' ? 'bg-accent-red text-white' : 'bg-secondary text-black'
                }`}
              >
                {saving ? 'Processing...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
