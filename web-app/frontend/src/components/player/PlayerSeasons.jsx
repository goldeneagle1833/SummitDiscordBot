import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  getPlayerSeasons, createSeason, searchSeasons, joinSeason,
  leaveSeason, modifySeason, endSeason, deleteSeason,
  kickSeasonMember, reportSeasonMatch, getSeasonMembers, listAllAvatars,
} from '@/api/games'

// ── Shared modal shell ──────────────────────────────────────────

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-bg-surface border border-border rounded-lg w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
            <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xl leading-none">&times;</button>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}

// ── Create Season Modal ─────────────────────────────────────────

function CreateSeasonModal({ onClose, onCreated }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [kValue, setKValue] = useState('32')
  const [baseElo, setBaseElo] = useState('1500')
  const [maxMembers, setMaxMembers] = useState('')
  const [region, setRegion] = useState('')
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const today = new Date().toISOString().slice(0, 10)

  const handleSubmit = async () => {
    if (!title.trim()) { setError('Title is required'); return }
    if (!startDate || !endDate) { setError('Start and end dates are required'); return }
    setSaving(true)
    setError(null)
    try {
      await createSeason({
        title: title.trim(),
        description: description.trim() || undefined,
        start_date: startDate,
        end_date: endDate,
        k_value: parseInt(kValue) || 32,
        base_elo: parseInt(baseElo) || 1500,
        max_members: maxMembers ? parseInt(maxMembers) : undefined,
        region: region.trim() || undefined,
      })
      onCreated()
      onClose()
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  return (
    <Modal title="Create Season" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="text-xs text-text-muted block mb-1">Title *</label>
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100}
            placeholder="e.g. Portland Winter League"
            className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">Description</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500}
            placeholder="Optional description..." rows={2}
            className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm resize-none" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted block mb-1">Start Date *</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} min={today}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">End Date *</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} min={startDate || today}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted block mb-1">K-Value</label>
            <input type="number" value={kValue} onChange={(e) => setKValue(e.target.value)} min={1} max={64}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
            <span className="text-[10px] text-text-muted">ELO sensitivity (1-64)</span>
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Base ELO</label>
            <input type="number" value={baseElo} onChange={(e) => setBaseElo(e.target.value)} min={0} max={3000}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
            <span className="text-[10px] text-text-muted">Starting ELO (0 to disable)</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted block mb-1">Max Members</label>
            <input type="number" value={maxMembers} onChange={(e) => setMaxMembers(e.target.value)} min={2}
              placeholder="Unlimited"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Region</label>
            <input type="text" value={region} onChange={(e) => setRegion(e.target.value)} maxLength={100}
              placeholder="e.g. Portland, OR"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
          </div>
        </div>
      </div>
      {error && <p className="text-xs text-accent-red mt-3">{error}</p>}
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary">Cancel</button>
        <button onClick={handleSubmit} disabled={saving}
          className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40">
          {saving ? 'Creating...' : 'Create Season'}
        </button>
      </div>
    </Modal>
  )
}

// ── Join Season Modal ──────────────��────────────────────────────

function JoinSeasonModal({ onClose, onJoined }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [joining, setJoining] = useState(null)
  const [error, setError] = useState(null)
  const timer = useRef(null)

  const doSearch = (q) => {
    setQuery(q)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      searchSeasons(q).then((d) => setResults(d.seasons || [])).catch(() => {})
    }, 300)
  }

  useEffect(() => {
    searchSeasons('').then((d) => setResults(d.seasons || [])).catch(() => {})
  }, [])

  const handleJoin = async (seasonId) => {
    setJoining(seasonId)
    setError(null)
    try {
      await joinSeason(seasonId)
      onJoined()
      onClose()
    } catch (err) { setError(err.message) }
    finally { setJoining(null) }
  }

  return (
    <Modal title="Join Season" onClose={onClose}>
      <input type="text" value={query} onChange={(e) => doSearch(e.target.value)}
        placeholder="Search seasons by name..."
        className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3" />
      {error && <p className="text-xs text-accent-red mb-2">{error}</p>}
      <div className="max-h-80 overflow-y-auto space-y-2">
        {results.length === 0 ? (
          <p className="text-text-muted text-sm text-center py-4">No seasons found</p>
        ) : results.map((s) => (
          <div key={s.season_id} className="bg-bg-raised border border-border rounded p-3 flex justify-between items-center">
            <div>
              <p className="text-sm font-medium text-text-primary">{s.title}</p>
              <p className="text-xs text-text-muted">
                {s.start_date} - {s.end_date}
                {s.region && ` | ${s.region}`}
                {s.member_count != null && ` | ${s.member_count} members`}
              </p>
            </div>
            {s.is_member ? (
              <span className="text-xs text-accent-green">Joined</span>
            ) : (
              <button onClick={() => handleJoin(s.season_id)} disabled={joining === s.season_id}
                className="px-3 py-1 text-xs bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40">
                {joining === s.season_id ? '...' : 'Join'}
              </button>
            )}
          </div>
        ))}
      </div>
    </Modal>
  )
}

// ── Modify Season Modal ───────────���─────────────────────────────

function ModifySeasonModal({ season, onClose, onModified }) {
  const [endDate, setEndDate] = useState(season.end_date)
  const [description, setDescription] = useState(season.description || '')
  const [kValueField, setKValueField] = useState(String(season.k_value))
  const [maxMembersField, setMaxMembersField] = useState(season.max_members ? String(season.max_members) : '')
  const [regionField, setRegionField] = useState(season.region || '')
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async () => {
    setSaving(true)
    setError(null)
    try {
      const fields = {}
      if (endDate !== season.end_date) fields.end_date = endDate
      if (description !== (season.description || '')) fields.description = description
      if (kValueField !== String(season.k_value)) fields.k_value = parseInt(kValueField)
      if (maxMembersField !== (season.max_members ? String(season.max_members) : ''))
        fields.max_members = maxMembersField ? parseInt(maxMembersField) : null
      if (regionField !== (season.region || '')) fields.region = regionField || null
      if (Object.keys(fields).length === 0) { onClose(); return }
      await modifySeason(season.season_id, fields)
      onModified()
      onClose()
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  return (
    <Modal title="Modify Season" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="text-xs text-text-muted block mb-1">Description</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} rows={2}
            className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm resize-none" />
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">End Date</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
            className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-text-muted block mb-1">K-Value</label>
            <input type="number" value={kValueField} onChange={(e) => setKValueField(e.target.value)} min={1} max={64}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Max Members</label>
            <input type="number" value={maxMembersField} onChange={(e) => setMaxMembersField(e.target.value)} min={2}
              placeholder="Unlimited"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Region</label>
            <input type="text" value={regionField} onChange={(e) => setRegionField(e.target.value)} maxLength={100}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm" />
          </div>
        </div>
      </div>
      {error && <p className="text-xs text-accent-red mt-3">{error}</p>}
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary">Cancel</button>
        <button onClick={handleSubmit} disabled={saving}
          className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40">
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </Modal>
  )
}

// ── Kick Member Modal ───────────────────────────────────────────

function KickMemberModal({ seasonId, onClose, onKicked }) {
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [kicking, setKicking] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getSeasonMembers(seasonId)
      .then((d) => setMembers(d.members || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [seasonId])

  const handleKick = async (userId, name) => {
    if (!confirm(`Kick ${name} from the season?`)) return
    setKicking(userId)
    setError(null)
    try {
      await kickSeasonMember(seasonId, userId)
      setMembers((m) => m.filter((x) => x.user_id !== userId))
      onKicked()
    } catch (err) { setError(err.message) }
    finally { setKicking(null) }
  }

  return (
    <Modal title="Kick Member" onClose={onClose}>
      {error && <p className="text-xs text-accent-red mb-2">{error}</p>}
      {loading ? (
        <p className="text-sm text-text-muted text-center py-4">Loading members...</p>
      ) : members.length === 0 ? (
        <p className="text-sm text-text-muted text-center py-4">No members</p>
      ) : (
        <div className="max-h-80 overflow-y-auto space-y-2">
          {members.map((m) => (
            <div key={m.user_id} className="bg-bg-raised border border-border rounded p-3 flex justify-between items-center">
              <div>
                <p className="text-sm text-text-primary">{m.display_name}</p>
                <p className="text-xs text-text-muted">ELO: {m.season_elo} | {m.wins}W-{m.losses}L</p>
              </div>
              <button onClick={() => handleKick(m.user_id, m.display_name)} disabled={kicking === m.user_id}
                className="px-3 py-1 text-xs bg-accent-red/20 text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/30 disabled:opacity-40">
                {kicking === m.user_id ? '...' : 'Kick'}
              </button>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

// ── Report Season Match Modal ──────────���────────────────────────

function ReportSeasonMatchModal({ seasonId, onClose, onReported }) {
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [winnerId, setWinnerId] = useState('')
  const [loserId, setLoserId] = useState('')
  const [winnerAvatar, setWinnerAvatar] = useState('')
  const [loserAvatar, setLoserAvatar] = useState('')
  const [avatars, setAvatars] = useState([])
  const [avatarSpecificEvent, setAvatarSpecificEvent] = useState(false)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([getSeasonMembers(seasonId), listAllAvatars()])
      .then(([d, avatarList]) => {
        setMembers(d.members || [])
        setAvatarSpecificEvent(Boolean(d.avatar_specific_event))
        setAvatars(avatarList || [])
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [seasonId])

  const handleSubmit = async () => {
    if (!winnerId || !loserId) { setError('Select both winner and loser'); return }
    if (winnerId === loserId) { setError('Winner and loser must be different'); return }
    if (avatarSpecificEvent && (!winnerAvatar || !loserAvatar)) {
      setError('Select the avatar played by both players for the active event')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await reportSeasonMatch(
        seasonId, winnerId, loserId, winnerAvatar, loserAvatar
      )
      onReported()
      onClose()
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  return (
    <Modal title="Report Match" onClose={onClose}>
      {loading ? (
        <p className="text-sm text-text-muted text-center py-4">Loading members...</p>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-text-muted block mb-1">Winner *</label>
            <select value={winnerId} onChange={(e) => setWinnerId(e.target.value)}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm">
              <option value="">Select winner...</option>
              {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Loser *</label>
            <select value={loserId} onChange={(e) => setLoserId(e.target.value)}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm">
              <option value="">Select loser...</option>
              {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
            </select>
          </div>
          {avatarSpecificEvent && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded border border-secondary/30 bg-secondary/5 p-3">
              <p className="sm:col-span-2 text-xs text-text-muted">
                The active event uses avatar-specific ELO. Select the avatars actually played.
              </p>
              <div>
                <label className="text-xs text-text-muted block mb-1">Winner Avatar *</label>
                <select value={winnerAvatar} onChange={(e) => setWinnerAvatar(e.target.value)}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm">
                  <option value="">Select avatar...</option>
                  {avatars.map((avatar) => <option key={avatar} value={avatar}>{avatar}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Loser Avatar *</label>
                <select value={loserAvatar} onChange={(e) => setLoserAvatar(e.target.value)}
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm">
                  <option value="">Select avatar...</option>
                  {avatars.map((avatar) => <option key={avatar} value={avatar}>{avatar}</option>)}
                </select>
              </div>
            </div>
          )}
        </div>
      )}
      {error && <p className="text-xs text-accent-red mt-3">{error}</p>}
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary">Cancel</button>
        <button onClick={handleSubmit} disabled={saving}
          className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40">
          {saving ? 'Reporting...' : 'Report Match'}
        </button>
      </div>
    </Modal>
  )
}

// ── Season Card ─────────────────────────────────────────────────

function SeasonCard({ season, isOwner, onRefresh }) {
  const [modal, setModal] = useState(null) // 'modify' | 'kick' | 'report'
  const [busy, setBusy] = useState(false)

  const statusLabel = season.status === 'active'
    ? (season.start_date > new Date().toISOString().slice(0, 10) ? 'Upcoming' : 'Active')
    : season.status

  const handleLeave = async () => {
    if (!confirm(`Leave "${season.title}"?`)) return
    setBusy(true)
    try { await leaveSeason(season.season_id); onRefresh() }
    catch (err) { alert(err.message) }
    finally { setBusy(false) }
  }

  const handleEnd = async () => {
    if (!confirm(`End "${season.title}"? This cannot be undone.`)) return
    setBusy(true)
    try { await endSeason(season.season_id); onRefresh() }
    catch (err) { alert(err.message) }
    finally { setBusy(false) }
  }

  const handleDelete = async () => {
    if (!confirm(`Delete "${season.title}"? All data will be lost.`)) return
    setBusy(true)
    try { await deleteSeason(season.season_id); onRefresh() }
    catch (err) { alert(err.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <div className="bg-accent-blue/[0.08] border border-accent-blue/25 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-base">🏆</span>
          <h4 className="text-[1.05rem] font-semibold text-text-primary">{season.title}</h4>
          <span className="text-xs px-2 py-0.5 rounded bg-accent-blue/15 text-accent-blue">{statusLabel}</span>
        </div>
        {season.description && (
          <p className="text-sm text-text-muted mt-1 mb-2">{season.description}</p>
        )}
        <div className="flex flex-wrap gap-4 text-sm mt-2">
          <span>📅 {season.start_date} — {season.end_date}</span>
          {season.region && <span>📍 {season.region}</span>}
        </div>
        <div className="flex flex-wrap gap-5 text-sm mt-2">
          <span><strong>ELO:</strong> {season.season_elo}</span>
          <span><strong>Record:</strong> {season.wins}W - {season.losses}L</span>
          <span><strong>Rank:</strong> #{season.rank} of {season.member_count}</span>
        </div>
        <div className="flex flex-wrap gap-2 mt-3">
          <Link to={`/season/${season.season_id}`}
            className="px-3 py-1 text-xs bg-secondary text-black rounded hover:opacity-90 no-underline">
            View Leaderboard
          </Link>
          {isOwner && season.is_creator && (
            <>
              <button onClick={() => setModal('modify')} disabled={busy}
                className="px-3 py-1 text-xs bg-bg-raised border border-border rounded hover:border-secondary">
                Modify Season
              </button>
              <button onClick={handleEnd} disabled={busy}
                className="px-3 py-1 text-xs bg-bg-raised border border-border rounded hover:border-secondary">
                End Season
              </button>
              <button onClick={handleDelete} disabled={busy}
                className="px-3 py-1 text-xs bg-accent-red/20 text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/30">
                Delete Season
              </button>
              <button onClick={() => setModal('kick')} disabled={busy}
                className="px-3 py-1 text-xs bg-bg-raised border border-border rounded hover:border-secondary">
                Kick Member
              </button>
              <button onClick={() => setModal('report')} disabled={busy}
                className="px-3 py-1 text-xs bg-secondary text-black rounded hover:opacity-90">
                Report Match
              </button>
            </>
          )}
          {isOwner && !season.is_creator && (
            <button onClick={handleLeave} disabled={busy}
              className="px-3 py-1 text-xs bg-accent-red/20 text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/30">
              Leave Season
            </button>
          )}
        </div>
      </div>

      {modal === 'modify' && (
        <ModifySeasonModal season={season} onClose={() => setModal(null)} onModified={onRefresh} />
      )}
      {modal === 'kick' && (
        <KickMemberModal seasonId={season.season_id} onClose={() => setModal(null)} onKicked={onRefresh} />
      )}
      {modal === 'report' && (
        <ReportSeasonMatchModal seasonId={season.season_id} onClose={() => setModal(null)} onReported={onRefresh} />
      )}
    </>
  )
}

// ── Main Component ────────��─────────────────────────────────────

export default function PlayerSeasons({ playerId, isOwner }) {
  const [seasons, setSeasons] = useState([])
  const [modal, setModal] = useState(null) // 'create' | 'join'

  const fetchSeasons = () => {
    getPlayerSeasons(playerId)
      .then((d) => setSeasons(d.seasons || []))
      .catch(() => {})
  }

  useEffect(() => { fetchSeasons() }, [playerId])

  return (
    <section>
      {isOwner && (
        <div className="flex gap-2 mb-3">
          <button onClick={() => setModal('create')}
            className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90">
            Create Season
          </button>
          <button onClick={() => setModal('join')}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary">
            Join Season
          </button>
        </div>
      )}

      {seasons.length > 0 && (
        <div className="space-y-3">
          {seasons.map((s) => (
            <SeasonCard key={s.season_id} season={s} isOwner={isOwner} onRefresh={fetchSeasons} />
          ))}
        </div>
      )}

      {modal === 'create' && (
        <CreateSeasonModal onClose={() => setModal(null)} onCreated={fetchSeasons} />
      )}
      {modal === 'join' && (
        <JoinSeasonModal onClose={() => setModal(null)} onJoined={fetchSeasons} />
      )}
    </section>
  )
}
