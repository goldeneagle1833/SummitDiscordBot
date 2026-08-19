import { useState, useEffect, useRef } from 'react'
import { recordGame, submitMatchReport, searchOpponents, listAllAvatars, getPlayerSeasons } from '@/api/games'
import { get } from '@/api/client'

export default function ReportGameModal({ playerId, onClose, onReported, initialLifeSubmitter, initialLifeOpponent }) {
  const [mode, setMode] = useState('ranked')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  // Shared fields
  const [deckUrl, setDeckUrl] = useState('')
  const [playerAvatar, setPlayerAvatar] = useState('')
  const [avatarSpecificEvent, setAvatarSpecificEvent] = useState(false)
  const [result, setResult] = useState(null)
  const [wentFirst, setWentFirst] = useState(null)

  // Ranked/Casual fields
  const [opponentQuery, setOpponentQuery] = useState('')
  const [opponentResults, setOpponentResults] = useState([])
  const [selectedOpponent, setSelectedOpponent] = useState(null)
  const [lifeSubmitter, setLifeSubmitter] = useState(initialLifeSubmitter != null ? String(initialLifeSubmitter) : '')
  const [lifeOpponent, setLifeOpponent] = useState(initialLifeOpponent != null ? String(initialLifeOpponent) : '')
  const [seasons, setSeasons] = useState([])
  const [selectedSeason, setSelectedSeason] = useState(null)
  const searchTimer = useRef(null)

  // Solo fields
  const [avatars, setAvatars] = useState([])
  const [opponentAvatar, setOpponentAvatar] = useState('')
  const [matchTime, setMatchTime] = useState('')
  const [matchComment, setMatchComment] = useState('')

  useEffect(() => {
    listAllAvatars().then(setAvatars).catch(() => {})
    get('/api/events')
      .then((d) => setAvatarSpecificEvent(Boolean(d.active_event?.avatar_specific)))
      .catch(() => {})
    getPlayerSeasons(playerId).then((d) => setSeasons(d.seasons || [])).catch(() => {})
  }, [playerId])

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const searchOpp = (query) => {
    setOpponentQuery(query)
    setSelectedOpponent(null)
    clearTimeout(searchTimer.current)
    if (query.length < 2) { setOpponentResults([]); return }
    searchTimer.current = setTimeout(() => {
      searchOpponents(query).then((d) => setOpponentResults(d.opponents || [])).catch(() => {})
    }, 300)
  }

  const selectOpp = (opp) => {
    setSelectedOpponent(opp)
    setOpponentQuery(opp.display_name)
    setOpponentResults([])
  }

  const resetForm = () => {
    setDeckUrl(''); setPlayerAvatar(''); setResult(null); setWentFirst(null)
    setOpponentQuery(''); setSelectedOpponent(null); setOpponentResults([])
    setLifeSubmitter(''); setLifeOpponent('')
    setSelectedSeason(null); setOpponentAvatar('')
    setMatchTime(''); setMatchComment('')
    setError(null); setSuccess(null)
  }

  const handleSubmit = async () => {
    setError(null); setSuccess(null)

    if (mode === 'solo') {
      if (!deckUrl.trim()) { setError('Deck URL is required.'); return }
      if (!opponentAvatar) { setError('Select an opponent avatar.'); return }
      if (result === null) { setError('Select a result.'); return }
      if (wentFirst === null) { setError('Select play/draw.'); return }
      setSaving(true)
      try {
        await recordGame({
          deck_url: deckUrl.trim(),
          opponent_avatar: opponentAvatar,
          did_win: result === 'won',
          went_first: wentFirst === 'first',
          match_time: matchTime ? parseInt(matchTime) : 0,
          match_comment: matchComment,
        })
        setSuccess('Game recorded!')
        onReported?.()
        setTimeout(onClose, 1200)
      } catch (err) { setError(err.message) }
      finally { setSaving(false) }
    } else {
      if (!selectedOpponent) { setError('Select an opponent.'); return }
      if (result === null) { setError('Select a result.'); return }
      if (wentFirst === null) { setError('Select play/draw.'); return }
      if (mode === 'ranked' && avatarSpecificEvent && !deckUrl.trim() && !playerAvatar) {
        setError('Provide a Curiosa deck URL or select the avatar you played for this event.')
        return
      }
      if (mode === 'ranked' && avatarSpecificEvent && !opponentAvatar) {
        setError("Select the avatar your opponent played so they can verify it.")
        return
      }
      setSaving(true)
      try {
        await submitMatchReport({
          opponent_user_id: selectedOpponent.user_id,
          result: result === 'won' ? 'won' : 'lost',
          went_first: wentFirst === 'first' ? 'submitter' : 'opponent',
          submitter_deck_url: deckUrl.trim() || undefined,
          submitter_avatar: playerAvatar || undefined,
          opponent_avatar: opponentAvatar || undefined,
          final_life_submitter: lifeSubmitter ? parseInt(lifeSubmitter) : 0,
          final_life_opponent: lifeOpponent ? parseInt(lifeOpponent) : 0,
          match_type: mode,
          season_id: selectedSeason?.season_id || undefined,
          match_comment: matchComment.trim() || undefined,
        })
        setSuccess('Match report submitted! Awaiting opponent confirmation.')
        onReported?.()
        setTimeout(onClose, 2000)
      } catch (err) { setError(err.message) }
      finally { setSaving(false) }
    }
  }

  const btnClass = (active) =>
    `px-3 py-1.5 text-xs font-medium border rounded transition-colors ${
      active ? 'bg-secondary text-black border-secondary' : 'bg-bg-raised border-border text-text-muted hover:text-text-primary'
    }`

  const tabClass = (active) =>
    `px-4 py-2 text-sm font-medium transition-colors ${
      active ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
    }`

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="p-6">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Report a Game</h3>

          {/* Mode Tabs */}
          <div className="inline-flex bg-bg-raised border border-border rounded-lg overflow-hidden mb-5">
            <button className={tabClass(mode === 'ranked')} onClick={() => { setMode('ranked'); resetForm() }}>Ranked</button>
            <button className={tabClass(mode === 'casual')} onClick={() => { setMode('casual'); resetForm() }}>Casual</button>
            <button className={tabClass(mode === 'solo')} onClick={() => { setMode('solo'); resetForm() }}>Solo</button>
          </div>

          {mode !== 'solo' ? (
            <>
              {/* Opponent Search */}
              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Opponent</label>
                <div className="relative">
                  <input
                    type="text"
                    value={opponentQuery}
                    onChange={(e) => searchOpp(e.target.value)}
                    placeholder="Search for opponent..."
                    className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                  />
                  {opponentResults.length > 0 && !selectedOpponent && (
                    <div className="absolute z-10 w-full mt-1 bg-bg-surface border border-border rounded shadow-lg max-h-40 overflow-y-auto">
                      {opponentResults.map((opp) => (
                        <button
                          key={opp.user_id}
                          onClick={() => selectOpp(opp)}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-bg-raised"
                        >
                          {opp.display_name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {selectedOpponent && (
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-accent-green">Selected: {selectedOpponent.display_name}</span>
                    <button onClick={() => { setSelectedOpponent(null); setOpponentQuery('') }} className="text-xs text-text-muted hover:text-accent-red">&times;</button>
                  </div>
                )}
              </div>

              {/* Deck URL */}
              {mode === 'ranked' && avatarSpecificEvent && (
                <div className="mb-4 rounded border border-secondary/30 bg-secondary/5 p-3 text-xs text-text-muted">
                  This event uses avatar-specific ELO. Your avatar must be detected from a Curiosa deck or selected below, and your opponent will verify both avatars.
                </div>
              )}
              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Deck URL (optional)</label>
                <input
                  type="url"
                  value={deckUrl}
                  onChange={(e) => setDeckUrl(e.target.value)}
                  placeholder="https://curiosa.io/decks/..."
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                />
              </div>

              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">
                  Your Avatar {mode === 'ranked' && avatarSpecificEvent ? '(required if no deck URL)' : '(optional override)'}
                </label>
                <select
                  value={playerAvatar}
                  onChange={(e) => setPlayerAvatar(e.target.value)}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                >
                  <option value="">Detect from Curiosa deck</option>
                  {avatars.map((avatar) => <option key={avatar} value={avatar}>{avatar}</option>)}
                </select>
              </div>

              {mode === 'ranked' && avatarSpecificEvent && (
                <div className="mb-4">
                  <label className="text-xs text-text-muted block mb-1">Opponent Avatar (required)</label>
                  <select
                    value={opponentAvatar}
                    onChange={(e) => setOpponentAvatar(e.target.value)}
                    className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                  >
                    <option value="">Select avatar...</option>
                    {avatars.map((avatar) => <option key={avatar} value={avatar}>{avatar}</option>)}
                  </select>
                </div>
              )}

              {/* Result */}
              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Result</label>
                <div className="flex gap-2">
                  <button className={btnClass(result === 'won')} onClick={() => setResult('won')}>Won</button>
                  <button className={btnClass(result === 'lost')} onClick={() => setResult('lost')}>Lost</button>
                </div>
              </div>

              {/* Turn Order */}
              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Turn Order</label>
                <div className="flex gap-2">
                  <button className={btnClass(wentFirst === 'first')} onClick={() => setWentFirst('first')}>I went first</button>
                  <button className={btnClass(wentFirst === 'second')} onClick={() => setWentFirst('second')}>Opponent went first</button>
                </div>
              </div>

              {/* Life Totals */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-text-muted block mb-1">Your Final Life (optional)</label>
                  <input type="number" value={lifeSubmitter} onChange={(e) => setLifeSubmitter(e.target.value)}
                    className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-text-muted block mb-1">Opponent's Final Life (optional)</label>
                  <input type="number" value={lifeOpponent} onChange={(e) => setLifeOpponent(e.target.value)}
                    className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
                </div>
              </div>

              {/* Match Comments */}
              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Match Comments (optional)</label>
                <textarea
                  value={matchComment}
                  onChange={(e) => setMatchComment(e.target.value)}
                  placeholder="Any notes about the match?"
                  rows={2}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm resize-none"
                />
              </div>

              {/* Season */}
              {seasons.length > 0 && (
                <div className="mb-4">
                  <label className="text-xs text-text-muted block mb-1">Season (optional)</label>
                  <select
                    value={selectedSeason?.season_id || ''}
                    onChange={(e) => setSelectedSeason(seasons.find((s) => String(s.season_id) === e.target.value) || null)}
                    className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                  >
                    <option value="">None</option>
                    {seasons.map((s) => (
                      <option key={s.season_id} value={s.season_id}>{s.title}</option>
                    ))}
                  </select>
                </div>
              )}
            </>
          ) : (
            <>
              {/* Solo Mode */}
              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Deck URL *</label>
                <input
                  type="url"
                  value={deckUrl}
                  onChange={(e) => setDeckUrl(e.target.value)}
                  placeholder="https://curiosa.io/decks/..."
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                />
              </div>

              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Opponent Avatar *</label>
                <select
                  value={opponentAvatar}
                  onChange={(e) => setOpponentAvatar(e.target.value)}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm"
                >
                  <option value="">Select avatar...</option>
                  {avatars.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>

              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Result *</label>
                <div className="flex gap-2">
                  <button className={btnClass(result === 'won')} onClick={() => setResult('won')}>Won</button>
                  <button className={btnClass(result === 'lost')} onClick={() => setResult('lost')}>Lost</button>
                </div>
              </div>

              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Turn Order *</label>
                <div className="flex gap-2">
                  <button className={btnClass(wentFirst === 'first')} onClick={() => setWentFirst('first')}>I went first</button>
                  <button className={btnClass(wentFirst === 'second')} onClick={() => setWentFirst('second')}>Opponent went first</button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-text-muted block mb-1">Match Duration (min)</label>
                  <input type="number" value={matchTime} onChange={(e) => setMatchTime(e.target.value)}
                    className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
                </div>
              </div>

              <div className="mb-4">
                <label className="text-xs text-text-muted block mb-1">Match Notes</label>
                <textarea
                  value={matchComment}
                  onChange={(e) => setMatchComment(e.target.value)}
                  rows={2}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm resize-none"
                />
              </div>
            </>
          )}

          {error && <p className="text-xs text-accent-red mb-3">{error}</p>}
          {success && <p className="text-xs text-accent-green mb-3">{success}</p>}

          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary">
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
            >
              {saving ? 'Submitting...' : 'Submit'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
