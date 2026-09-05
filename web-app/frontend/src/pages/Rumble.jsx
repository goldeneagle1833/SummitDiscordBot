import { useState, useEffect, useCallback } from 'react'
import { get, post, put, del } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'

function PrizeWall({ prizes, earnings, userBones, userId, onRedeem }) {
  const matchEarnings = earnings?.filter((e) => e.category === 'match') || []
  const outsideEarnings = earnings?.filter((e) => e.category === 'outside') || []

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h2 className="text-lg font-semibold text-text-primary mb-4 text-center">Rumble Rewards</h2>

      {/* Earnings Tables */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {matchEarnings.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-text-muted mb-2 uppercase tracking-wide">Match Earnings</h3>
            <div className="space-y-1">
              {matchEarnings.map((e) => (
                <div key={e.key} className="flex justify-between text-sm">
                  <span>{e.label}</span>
                  <span className="font-mono">{e.bones} bone{e.bones !== 1 ? 's' : ''}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {outsideEarnings.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-text-muted mb-2 uppercase tracking-wide">Outside-Rumble Earnings</h3>
            <div className="space-y-1">
              {outsideEarnings.map((e) => (
                <div key={e.key} className="flex justify-between text-sm">
                  <span>{e.label}</span>
                  <span className="font-mono">{e.bones} bone{e.bones !== 1 ? 's' : ''}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Prize Wall */}
      {prizes?.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-text-muted mb-2 uppercase tracking-wide text-center">Prize Wall</h3>
          {userId && userBones !== null && (
            <p className="text-center text-sm text-text-muted mb-2">
              Your balance: <span className="font-mono font-semibold text-text-primary">{userBones}</span> bone{userBones !== 1 ? 's' : ''}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Prize</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Cost</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Stock</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Description</th>
                  {userId && <th className="py-1.5 px-2 text-text-muted font-semibold"></th>}
                </tr>
              </thead>
              <tbody>
                {prizes.map((p) => {
                  const canAfford = userBones !== null && userBones >= p.cost && p.cost > 0
                  const inStock = p.stock == null || p.stock > 0
                  return (
                    <tr key={p.id} className="border-b border-border/50">
                      <td className="py-1.5 px-2 font-medium">{p.name}</td>
                      <td className="py-1.5 px-2 font-mono">
                        {p.cost > 0 ? `${p.cost} bone${p.cost !== 1 ? 's' : ''}` : 'TBD'}
                      </td>
                      <td className="py-1.5 px-2 text-text-muted">
                        {p.stock != null ? p.stock : 'Unlimited'}
                      </td>
                      <td className="py-1.5 px-2 text-text-muted text-xs">{p.description || '-'}</td>
                      {userId && (
                        <td className="py-1.5 px-2">
                          {p.cost > 0 && inStock ? (
                            <button
                              onClick={() => onRedeem(p.id, p.name, p.cost)}
                              disabled={!canAfford}
                              className={`text-xs px-2 py-0.5 rounded font-medium ${
                                canAfford
                                  ? 'bg-secondary text-black hover:opacity-90'
                                  : 'bg-border text-text-muted cursor-not-allowed'
                              }`}
                            >
                              Redeem
                            </button>
                          ) : !inStock ? (
                            <span className="text-xs text-text-muted">Sold out</span>
                          ) : null}
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function EditPlayerModal({ player, onClose, onSave, onDelete }) {
  const [displayName, setDisplayName] = useState(player.display_name || '')
  const [wins, setWins] = useState(player.wins)
  const [losses, setLosses] = useState(player.losses)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await onSave(player.user_id, {
      display_name: displayName,
      wins: parseInt(wins) || 0,
      losses: parseInt(losses) || 0,
    })
    setSaving(false)
  }

  const handleDelete = async () => {
    if (!confirm(`Delete all rumble records for "${player.display_name}"? This cannot be undone.`)) return
    setSaving(true)
    await onDelete(player.user_id)
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-sm mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text-primary mb-4">Edit Player</h3>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-text-muted mb-1">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text-muted mb-1">Wins</label>
              <input
                type="number"
                min="0"
                value={wins}
                onChange={(e) => setWins(e.target.value)}
                className="w-full bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Losses</label>
              <input
                type="number"
                min="0"
                value={losses}
                onChange={(e) => setLosses(e.target.value)}
                className="w-full bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
            </div>
          </div>
        </div>
        <div className="flex justify-between mt-5">
          <button
            onClick={handleDelete}
            disabled={saving}
            className="text-accent-red hover:text-accent-red/80 text-sm font-medium disabled:opacity-50"
          >
            Delete Entry
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-sm px-3 py-1.5"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-secondary text-black px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function EditBoneModal({ entry, onClose, onSave, onDelete }) {
  const [displayName, setDisplayName] = useState(entry.display_name || '')
  const [balance, setBalance] = useState(entry.balance)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await onSave(entry.discord_user_id, {
      display_name: displayName,
      balance: parseInt(balance) || 0,
    })
    setSaving(false)
  }

  const handleDelete = async () => {
    if (!confirm(`Delete bone entry for "${entry.display_name}"? This removes their balance and transaction history.`)) return
    setSaving(true)
    await onDelete(entry.discord_user_id)
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-sm mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text-primary mb-4">Edit Bone Entry</h3>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-text-muted mb-1">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Balance</label>
            <input
              type="number"
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
            />
          </div>
        </div>
        <div className="flex justify-between mt-5">
          <button
            onClick={handleDelete}
            disabled={saving}
            className="text-accent-red hover:text-accent-red/80 text-sm font-medium disabled:opacity-50"
          >
            Delete Entry
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-sm px-3 py-1.5"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-secondary text-black px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function BonesLeaderboard({ bones, isAdmin, onEdit }) {
  if (!bones?.length) return null
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h2 className="text-base font-semibold text-text-primary mb-3">Bone Balances</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-1.5 px-2 text-text-muted font-semibold w-8">#</th>
              <th className="py-1.5 px-2 text-text-muted font-semibold">Player</th>
              <th className="py-1.5 px-2 text-text-muted font-semibold">Bones</th>
            </tr>
          </thead>
          <tbody>
            {bones.map((b, i) => (
              <tr key={b.discord_user_id} className="border-b border-border/50">
                <td className="py-1.5 px-2 text-text-muted">{i + 1}</td>
                <td className="py-1.5 px-2 font-medium">
                  {b.display_name || 'Unknown'}
                  {isAdmin && (
                    <button
                      onClick={() => onEdit(b)}
                      className="ml-1.5 text-text-muted hover:text-secondary inline-block align-middle"
                      title="Edit entry"
                    >
                      &#9998;
                    </button>
                  )}
                </td>
                <td className="py-1.5 px-2 font-mono">{b.balance}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RedemptionHistory({ redemptions }) {
  if (!redemptions?.length) {
    return <p className="text-sm text-text-muted py-2">No redemptions yet.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="py-1.5 px-2 text-text-muted font-semibold">Player</th>
            <th className="py-1.5 px-2 text-text-muted font-semibold">Prize</th>
            <th className="py-1.5 px-2 text-text-muted font-semibold">Cost</th>
            <th className="py-1.5 px-2 text-text-muted font-semibold">Date</th>
          </tr>
        </thead>
        <tbody>
          {redemptions.map((r) => (
            <tr key={r.id} className="border-b border-border/50">
              <td className="py-1.5 px-2 font-medium">{r.display_name || 'Unknown'}</td>
              <td className="py-1.5 px-2">{r.prize_name || 'Deleted prize'}</td>
              <td className="py-1.5 px-2 font-mono">{r.cost}</td>
              <td className="py-1.5 px-2 text-text-muted">
                {r.created_at ? new Date(r.created_at + 'Z').toLocaleDateString() : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const EFFECT_ACTIONS = [
  { value: 'roll', label: 'Roll (score points)', fields: ['formula', 'points'] },
  { value: 'damage', label: 'Damage (hurt a target)', fields: ['target', 'formula'] },
  { value: 'syphon', label: 'Syphon (steal points)', fields: ['target', 'steal_percent'] },
  { value: 'protect', label: 'Protect (shield from attacks)', fields: ['duration', 'cost_type', 'cost_percent'] },
  { value: 'swap', label: 'Swap (trade scores)', fields: ['target'] },
  { value: 'block', label: 'Block (prevent actions)', fields: ['target', 'duration'] },
  { value: 'gamble', label: 'Gamble (risk points)', fields: ['win_chance', 'win_multiplier', 'lose_multiplier'] },
  { value: 'redistribute', label: 'Redistribute (take from group)', fields: ['from', 'to', 'percent'] },
  { value: 'bonus', label: 'Bonus (add flat points)', fields: ['amount'] },
  { value: 'trap', label: 'Trap (delayed effect)', fields: ['target', 'trigger', 'trap_effect'] },
  { value: 'buff', label: 'Buff (multiply next action)', fields: ['multiplier', 'duration'] },
  { value: 'combo', label: 'Combo (multiple effects)', fields: ['effects'] },
]

const EFFECT_TARGETS = [
  { value: 'leader', label: 'Leader' },
  { value: 'ahead_1', label: 'Player 1 ahead' },
  { value: 'random_ahead', label: 'Random (ahead)' },
  { value: 'random_behind', label: 'Random (behind)' },
  { value: 'random_any', label: 'Random (any)' },
  { value: 'all', label: 'All players' },
  { value: 'top5', label: 'Top 5' },
  { value: 'self', label: 'Self' },
  { value: 'specified', label: 'Specified by user' },
]

function EffectEditor({ value, onChange }) {
  const [rawMode, setRawMode] = useState(false)
  const [rawJson, setRawJson] = useState('')
  const [jsonError, setJsonError] = useState(null)

  const effect = value || {}
  const actionDef = EFFECT_ACTIONS.find((a) => a.value === effect.action)

  const update = (field, val) => {
    onChange({ ...effect, [field]: val })
  }

  const switchToRaw = () => {
    setRawJson(JSON.stringify(effect, null, 2))
    setJsonError(null)
    setRawMode(true)
  }

  const switchToVisual = () => {
    try {
      const parsed = JSON.parse(rawJson)
      onChange(parsed)
      setJsonError(null)
      setRawMode(false)
    } catch {
      setJsonError('Invalid JSON')
    }
  }

  const handleRawChange = (text) => {
    setRawJson(text)
    try {
      const parsed = JSON.parse(text)
      onChange(parsed)
      setJsonError(null)
    } catch {
      setJsonError('Invalid JSON')
    }
  }

  if (rawMode) {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <label className="block text-xs text-text-muted font-semibold">Effect (JSON)</label>
          <button type="button" onClick={switchToVisual} className="text-xs text-secondary hover:text-secondary/80">
            Visual Editor
          </button>
        </div>
        <textarea
          value={rawJson}
          onChange={(e) => handleRawChange(e.target.value)}
          rows={6}
          className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-xs font-mono"
          spellCheck={false}
        />
        {jsonError && <p className="text-xs text-accent-red">{jsonError}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="block text-xs text-text-muted font-semibold">Effect Logic</label>
        <button type="button" onClick={switchToRaw} className="text-xs text-secondary hover:text-secondary/80">
          Raw JSON
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-text-muted mb-0.5">Action</label>
          <select
            value={effect.action || ''}
            onChange={(e) => onChange({ action: e.target.value })}
            className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
          >
            <option value="">-- select --</option>
            {EFFECT_ACTIONS.map((a) => (
              <option key={a.value} value={a.value}>{a.label}</option>
            ))}
          </select>
        </div>
        {actionDef?.fields.includes('target') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Target</label>
            <select
              value={effect.target || ''}
              onChange={(e) => update('target', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            >
              <option value="">-- select --</option>
              {EFFECT_TARGETS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
        )}
        {actionDef?.fields.includes('formula') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Formula</label>
            <input
              type="text"
              placeholder="e.g. 1d100, 3d20/2"
              value={effect.formula || ''}
              onChange={(e) => update('formula', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('points') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Points Source</label>
            <input
              type="text"
              placeholder="e.g. roll_value, fixed"
              value={effect.points || ''}
              onChange={(e) => update('points', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('steal_percent') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Steal %</label>
            <input
              type="number"
              value={effect.steal_percent ?? ''}
              onChange={(e) => update('steal_percent', parseInt(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('duration') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Duration</label>
            <input
              type="text"
              placeholder="e.g. 24h, 1d, permanent"
              value={effect.duration || ''}
              onChange={(e) => update('duration', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('percent') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Percent</label>
            <input
              type="number"
              value={effect.percent ?? ''}
              onChange={(e) => update('percent', parseInt(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('cost_type') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Cost Type</label>
            <select
              value={effect.cost_type || 'flat'}
              onChange={(e) => update('cost_type', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            >
              <option value="flat">Flat</option>
              <option value="percent">Percent of score</option>
            </select>
          </div>
        )}
        {actionDef?.fields.includes('cost_percent') && effect.cost_type === 'percent' && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Cost %</label>
            <input
              type="number"
              value={effect.cost_percent ?? ''}
              onChange={(e) => update('cost_percent', parseInt(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('win_chance') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Win Chance %</label>
            <input
              type="number"
              value={effect.win_chance ?? ''}
              onChange={(e) => update('win_chance', parseInt(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('win_multiplier') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Win Multiplier</label>
            <input
              type="number"
              step="0.1"
              value={effect.win_multiplier ?? ''}
              onChange={(e) => update('win_multiplier', parseFloat(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('lose_multiplier') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Lose Multiplier</label>
            <input
              type="number"
              step="0.1"
              value={effect.lose_multiplier ?? ''}
              onChange={(e) => update('lose_multiplier', parseFloat(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('multiplier') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Multiplier</label>
            <input
              type="number"
              step="0.1"
              value={effect.multiplier ?? ''}
              onChange={(e) => update('multiplier', parseFloat(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('amount') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Amount</label>
            <input
              type="number"
              value={effect.amount ?? ''}
              onChange={(e) => update('amount', parseInt(e.target.value) || 0)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
        {actionDef?.fields.includes('from') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Take From</label>
            <select
              value={effect.from || ''}
              onChange={(e) => update('from', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            >
              <option value="">-- select --</option>
              <option value="others">All others</option>
              <option value="top5">Top 5</option>
              <option value="bottom5">Bottom 5</option>
            </select>
          </div>
        )}
        {actionDef?.fields.includes('to') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Give To</label>
            <select
              value={effect.to || ''}
              onChange={(e) => update('to', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            >
              <option value="">-- select --</option>
              <option value="self">Self</option>
              <option value="leader">Leader (fartlord)</option>
              <option value="top5">Top 5</option>
              <option value="bottom5">Bottom 5</option>
              <option value="all">All</option>
            </select>
          </div>
        )}
        {actionDef?.fields.includes('trigger') && (
          <div>
            <label className="block text-xs text-text-muted mb-0.5">Trigger</label>
            <input
              type="text"
              placeholder="e.g. on_fart, on_attack"
              value={effect.trigger || ''}
              onChange={(e) => update('trigger', e.target.value)}
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}
      </div>
      {(actionDef?.fields.includes('combo') || actionDef?.fields.includes('effects') || actionDef?.fields.includes('trap_effect')) && (
        <div>
          <p className="text-xs text-text-muted mb-1">
            Complex effects (combo/trap) &mdash; use Raw JSON to define nested effects.
          </p>
          <button type="button" onClick={switchToRaw} className="text-xs text-secondary hover:text-secondary/80">
            Switch to Raw JSON
          </button>
        </div>
      )}
      {effect.action && (
        <div className="mt-1 p-2 bg-bg-primary rounded border border-border/50">
          <p className="text-xs text-text-muted font-mono break-all">{JSON.stringify(effect)}</p>
        </div>
      )}
    </div>
  )
}

function FartAdmin({ data, onRefresh }) {
  const [activeTab, setActiveTab] = useState('overview')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)

  // New command form
  const [cmdName, setCmdName] = useState('')
  const [cmdLabel, setCmdLabel] = useState('')
  const [cmdDesc, setCmdDesc] = useState('')
  const [cmdCost, setCmdCost] = useState('')
  const [cmdDamage, setCmdDamage] = useState('')
  const [cmdCooldown, setCmdCooldown] = useState('daily')
  const [cmdEffect, setCmdEffect] = useState({})

  // Editing commands
  const [editingCmd, setEditingCmd] = useState(null)
  const [editForm, setEditForm] = useState({})

  // New shop item form
  const [shopName, setShopName] = useState('')
  const [shopLabel, setShopLabel] = useState('')
  const [shopDesc, setShopDesc] = useState('')
  const [shopCost, setShopCost] = useState('')
  const [shopDamage, setShopDamage] = useState('')
  const [shopCooldown, setShopCooldown] = useState('none')
  const [shopEffect, setShopEffect] = useState({})

  // Editing shop items
  const [editingShop, setEditingShop] = useState(null)
  const [shopEditForm, setShopEditForm] = useState({})

  const flash = (msg, isError = false) => {
    setMessage({ text: msg, error: isError })
    setTimeout(() => setMessage(null), 3000)
  }

  const handleReset = async () => {
    if (!confirm('Reset the entire fart game / season? This clears ALL scores, history, and every tracked cooldown/usage (daily, weekly, season, reign) — including items like !mushroom, actions like !bullfart, Evil Star locks, gifts/donations, and status effects. Shop/command config is kept. This cannot be undone.')) return
    setLoading(true)
    try {
      const res = await post('/api/rumble/admin/fart/reset')
      const total = Object.values(res.cleared).reduce((a, b) => a + b, 0)
      flash(`Game reset! ${total} records cleared.`)
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    } finally {
      setLoading(false)
    }
  }

  const handleEvilStart = async () => {
    if (!confirm('Evil Start: Same full game reset as Reset Fart Game, then give all players random chaotic scores (-250 to 250). Continue?')) return
    setLoading(true)
    try {
      const res = await post('/api/rumble/admin/fart/evil-start')
      flash(`Evil start! ${res.players_affected} players given chaotic scores.`)
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    } finally {
      setLoading(false)
    }
  }

  const handleAddCommand = async (e) => {
    e.preventDefault()
    if (!cmdName || !cmdLabel) return
    setLoading(true)
    try {
      await post('/api/rumble/admin/fart/commands', {
        name: cmdName,
        label: cmdLabel,
        description: cmdDesc || null,
        cost: cmdCost ? parseInt(cmdCost) : 0,
        damage: cmdDamage ? parseInt(cmdDamage) : 0,
        cooldown: cmdCooldown,
        effect: cmdEffect && Object.keys(cmdEffect).length > 0 ? cmdEffect : null,
      })
      flash('Command added')
      setCmdName('')
      setCmdLabel('')
      setCmdDesc('')
      setCmdCost('')
      setCmdDamage('')
      setCmdCooldown('daily')
      setCmdEffect({})
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateCommand = async (id, updates) => {
    try {
      await put(`/api/rumble/admin/fart/commands/${id}`, updates)
      flash('Command updated')
      setEditingCmd(null)
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const handleDeleteCommand = async (id) => {
    if (!confirm('Delete this command config?')) return
    try {
      await del(`/api/rumble/admin/fart/commands/${id}`)
      flash('Command deleted')
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const startEditing = (cmd) => {
    setEditingCmd(cmd.id)
    setEditForm({
      label: cmd.label,
      description: cmd.description || '',
      cost: cmd.cost,
      damage: cmd.damage,
      cooldown: cmd.cooldown,
      enabled: cmd.enabled,
      effect: cmd.effect || {},
    })
  }

  const saveEditing = (id) => {
    handleUpdateCommand(id, {
      label: editForm.label,
      description: editForm.description || null,
      cost: parseInt(editForm.cost) || 0,
      damage: parseInt(editForm.damage) || 0,
      cooldown: editForm.cooldown,
      enabled: editForm.enabled ? 1 : 0,
      effect: editForm.effect && Object.keys(editForm.effect).length > 0 ? editForm.effect : null,
    })
  }

  // --- Shop item handlers ---

  const handleAddShopItem = async (e) => {
    e.preventDefault()
    if (!shopName || !shopLabel) return
    setLoading(true)
    try {
      await post('/api/rumble/admin/fart/shop', {
        name: shopName,
        label: shopLabel,
        description: shopDesc || null,
        cost: shopCost ? parseInt(shopCost) : 0,
        damage: shopDamage ? parseInt(shopDamage) : 0,
        cooldown: shopCooldown,
        effect: shopEffect && Object.keys(shopEffect).length > 0 ? shopEffect : null,
      })
      flash('Shop item added')
      setShopName('')
      setShopLabel('')
      setShopDesc('')
      setShopCost('')
      setShopDamage('')
      setShopCooldown('none')
      setShopEffect({})
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateShopItem = async (id, updates) => {
    try {
      await put(`/api/rumble/admin/fart/shop/${id}`, updates)
      flash('Shop item updated')
      setEditingShop(null)
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const handleDeleteShopItem = async (id) => {
    if (!confirm('Delete this shop item?')) return
    try {
      await del(`/api/rumble/admin/fart/shop/${id}`)
      flash('Shop item deleted')
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const startEditingShop = (item) => {
    setEditingShop(item.id)
    setShopEditForm({
      label: item.label,
      description: item.description || '',
      cost: item.cost,
      damage: item.damage,
      cooldown: item.cooldown,
      enabled: item.enabled,
      effect: item.effect || {},
    })
  }

  const saveEditingShop = (id) => {
    handleUpdateShopItem(id, {
      label: shopEditForm.label,
      description: shopEditForm.description || null,
      cost: parseInt(shopEditForm.cost) || 0,
      damage: parseInt(shopEditForm.damage) || 0,
      cooldown: shopEditForm.cooldown,
      enabled: shopEditForm.enabled ? 1 : 0,
      effect: shopEditForm.effect && Object.keys(shopEditForm.effect).length > 0 ? shopEditForm.effect : null,
    })
  }

  const fartLeaderboard = data.fart_leaderboard || []
  const fartCommands = data.fart_commands || []
  const fartShopItems = data.fart_shop_items || []

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'commands', label: 'Commands' },
    { id: 'shop', label: 'Shop' },
    { id: 'actions', label: 'Actions' },
  ]

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h2 className="text-base font-semibold text-text-primary mb-3">Fart Game Admin</h2>

      {message && (
        <div className={`mb-3 p-2 rounded text-sm ${message.error ? 'bg-accent-red/20 text-accent-red' : 'bg-accent-green/20 text-accent-green'}`}>
          {message.text}
        </div>
      )}

      <div className="flex gap-2 mb-4 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`pb-2 px-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === t.id
                ? 'border-secondary text-secondary'
                : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview Tab - Fart Leaderboard */}
      {activeTab === 'overview' && (
        <div>
          {fartLeaderboard.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="py-1.5 px-2 text-text-muted font-semibold w-8">#</th>
                    <th className="py-1.5 px-2 text-text-muted font-semibold">Player</th>
                    <th className="py-1.5 px-2 text-text-muted font-semibold">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {fartLeaderboard.map((p) => (
                    <tr key={p.user_id} className="border-b border-border/50">
                      <td className="py-1.5 px-2 text-text-muted">{p.rank}</td>
                      <td className="py-1.5 px-2 font-medium">{p.username || 'Unknown'}</td>
                      <td className="py-1.5 px-2 font-mono">{p.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-text-muted text-sm">No fart scores yet.</p>
          )}
        </div>
      )}

      {/* Commands Tab */}
      {activeTab === 'commands' && (
        <div className="space-y-4">
          {/* Existing commands */}
          {fartCommands.map((cmd) => (
            <div key={cmd.id} className="border-b border-border/50 pb-2">
              {editingCmd === cmd.id ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Label</label>
                      <input
                        type="text"
                        value={editForm.label}
                        onChange={(e) => setEditForm({ ...editForm, label: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Cooldown</label>
                      <select
                        value={editForm.cooldown}
                        onChange={(e) => setEditForm({ ...editForm, cooldown: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      >
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                        <option value="once_per_reign">Once per reign</option>
                        <option value="none">None</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Cost</label>
                      <input
                        type="number"
                        value={editForm.cost}
                        onChange={(e) => setEditForm({ ...editForm, cost: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Damage / Value</label>
                      <input
                        type="number"
                        value={editForm.damage}
                        onChange={(e) => setEditForm({ ...editForm, damage: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-xs text-text-muted mb-0.5">Description</label>
                      <input
                        type="text"
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={!!editForm.enabled}
                          onChange={(e) => setEditForm({ ...editForm, enabled: e.target.checked ? 1 : 0 })}
                          className="rounded"
                        />
                        Enabled
                      </label>
                    </div>
                    <div className="col-span-2">
                      <EffectEditor
                        value={editForm.effect}
                        onChange={(eff) => setEditForm({ ...editForm, effect: eff })}
                      />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveEditing(cmd.id)}
                      className="bg-secondary text-black px-3 py-1 rounded text-xs font-medium hover:opacity-90"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingCmd(null)}
                      className="text-text-muted hover:text-text-primary text-xs px-3 py-1"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm">
                    <span className={`flex-1 font-medium ${!cmd.enabled ? 'line-through text-text-muted' : ''}`}>
                      !{cmd.name}
                      <span className="text-text-muted font-normal ml-1.5">({cmd.label})</span>
                    </span>
                    <span className="text-text-muted text-xs w-16 text-center" title="Cost">
                      {cmd.cost > 0 ? `${cmd.cost}c` : 'Free'}
                    </span>
                    <span className="text-text-muted text-xs w-16 text-center" title="Damage/Value">
                      {cmd.damage > 0 ? `${cmd.damage}d` : '-'}
                    </span>
                    <span className="text-text-muted text-xs w-20 text-center" title="Cooldown">
                      {cmd.cooldown.replace('_', ' ')}
                    </span>
                    <button
                      onClick={() => startEditing(cmd)}
                      className="text-secondary hover:text-secondary/80 text-xs px-2"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeleteCommand(cmd.id)}
                      className="text-accent-red hover:text-accent-red/80 text-xs px-2"
                    >
                      Delete
                    </button>
                  </div>
                  {cmd.effect?.action && (
                    <span className="inline-block text-xs px-1.5 py-0.5 rounded bg-secondary/10 text-secondary font-mono">
                      {cmd.effect.action}{cmd.effect.target ? ` → ${cmd.effect.target}` : ''}{cmd.effect.formula ? ` (${cmd.effect.formula})` : ''}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Add new command */}
          <form onSubmit={handleAddCommand} className="space-y-2 pt-2 border-t border-border">
            <p className="text-xs text-text-muted font-semibold uppercase">Add Command</p>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                placeholder="Command name (e.g. superfart)"
                value={cmdName}
                onChange={(e) => setCmdName(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
                required
              />
              <input
                type="text"
                placeholder="Display Label"
                value={cmdLabel}
                onChange={(e) => setCmdLabel(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
                required
              />
              <input
                type="number"
                placeholder="Cost (0 = free)"
                value={cmdCost}
                onChange={(e) => setCmdCost(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
              <input
                type="number"
                placeholder="Damage / Value"
                value={cmdDamage}
                onChange={(e) => setCmdDamage(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
              <select
                value={cmdCooldown}
                onChange={(e) => setCmdCooldown(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="once_per_reign">Once per reign</option>
                <option value="none">None</option>
              </select>
              <input
                type="text"
                placeholder="Description"
                value={cmdDesc}
                onChange={(e) => setCmdDesc(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
            </div>
            <EffectEditor value={cmdEffect} onChange={setCmdEffect} />
            <button
              type="submit"
              disabled={loading}
              className="bg-secondary text-black px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Add Command
            </button>
          </form>
        </div>
      )}

      {/* Shop Tab */}
      {activeTab === 'shop' && (
        <div className="space-y-4">
          {/* Existing shop items */}
          {fartShopItems.map((item) => (
            <div key={item.id} className="border-b border-border/50 pb-2">
              {editingShop === item.id ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Label</label>
                      <input
                        type="text"
                        value={shopEditForm.label}
                        onChange={(e) => setShopEditForm({ ...shopEditForm, label: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Cooldown</label>
                      <select
                        value={shopEditForm.cooldown}
                        onChange={(e) => setShopEditForm({ ...shopEditForm, cooldown: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      >
                        <option value="none">None</option>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Cost</label>
                      <input
                        type="number"
                        value={shopEditForm.cost}
                        onChange={(e) => setShopEditForm({ ...shopEditForm, cost: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-0.5">Damage</label>
                      <input
                        type="number"
                        value={shopEditForm.damage}
                        onChange={(e) => setShopEditForm({ ...shopEditForm, damage: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-xs text-text-muted mb-0.5">Description</label>
                      <input
                        type="text"
                        value={shopEditForm.description}
                        onChange={(e) => setShopEditForm({ ...shopEditForm, description: e.target.value })}
                        className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={!!shopEditForm.enabled}
                          onChange={(e) => setShopEditForm({ ...shopEditForm, enabled: e.target.checked ? 1 : 0 })}
                          className="rounded"
                        />
                        Enabled
                      </label>
                    </div>
                    <div className="col-span-2">
                      <EffectEditor
                        value={shopEditForm.effect}
                        onChange={(eff) => setShopEditForm({ ...shopEditForm, effect: eff })}
                      />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveEditingShop(item.id)}
                      className="bg-secondary text-black px-3 py-1 rounded text-xs font-medium hover:opacity-90"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingShop(null)}
                      className="text-text-muted hover:text-text-primary text-xs px-3 py-1"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm">
                    <span className={`flex-1 font-medium ${!item.enabled ? 'line-through text-text-muted' : ''}`}>
                      !{item.name}
                      <span className="text-text-muted font-normal ml-1.5">({item.label})</span>
                    </span>
                    <span className="text-text-muted text-xs w-16 text-center" title="Cost">
                      {item.cost > 0 ? `${item.cost}pts` : 'Free'}
                    </span>
                    <span className="text-text-muted text-xs w-16 text-center" title="Cooldown">
                      {item.cooldown === 'none' ? '-' : item.cooldown}
                    </span>
                    <button
                      onClick={() => startEditingShop(item)}
                      className="text-secondary hover:text-secondary/80 text-xs px-2"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeleteShopItem(item.id)}
                      className="text-accent-red hover:text-accent-red/80 text-xs px-2"
                    >
                      Delete
                    </button>
                  </div>
                  {item.effect?.action && (
                    <span className="inline-block text-xs px-1.5 py-0.5 rounded bg-secondary/10 text-secondary font-mono">
                      {item.effect.action}{item.effect.target ? ` → ${item.effect.target}` : ''}{item.effect.formula ? ` (${item.effect.formula})` : ''}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Add new shop item */}
          <form onSubmit={handleAddShopItem} className="space-y-2 pt-2 border-t border-border">
            <p className="text-xs text-text-muted font-semibold uppercase">Add Shop Item</p>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                placeholder="Item name (e.g. mega_fart)"
                value={shopName}
                onChange={(e) => setShopName(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
                required
              />
              <input
                type="text"
                placeholder="Display Label"
                value={shopLabel}
                onChange={(e) => setShopLabel(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
                required
              />
              <input
                type="number"
                placeholder="Cost (0 = free)"
                value={shopCost}
                onChange={(e) => setShopCost(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
              <input
                type="number"
                placeholder="Damage"
                value={shopDamage}
                onChange={(e) => setShopDamage(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
              <select
                value={shopCooldown}
                onChange={(e) => setShopCooldown(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              >
                <option value="none">No cooldown</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
              <input
                type="text"
                placeholder="Description"
                value={shopDesc}
                onChange={(e) => setShopDesc(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
            </div>
            <EffectEditor value={shopEffect} onChange={setShopEffect} />
            <button
              type="submit"
              disabled={loading}
              className="bg-secondary text-black px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Add Shop Item
            </button>
          </form>
        </div>
      )}

      {/* Actions Tab */}
      {activeTab === 'actions' && (
        <div className="space-y-4">
          <div className="p-3 border border-border rounded-lg">
            <h3 className="text-sm font-semibold mb-1">Reset Game</h3>
            <p className="text-xs text-text-muted mb-3">
              Wipe all gameplay state: scores, history, and every cooldown/usage lock (daily, weekly, season, reign) — mushroom, bullfart, taxes/wealth, Evil Star, gifts/donations, protections, and any other trackers. Keeps shop/command config. Players start a fresh season.
            </p>
            <button
              onClick={handleReset}
              disabled={loading}
              className="bg-accent-red text-white px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Reset Fart Game
            </button>
          </div>
          <div className="p-3 border border-border rounded-lg">
            <h3 className="text-sm font-semibold mb-1">Evil Start</h3>
            <p className="text-xs text-text-muted mb-3">
              Same full reset as Reset Fart Game, then give all existing players random chaotic starting scores between -250 and 250. Pure chaos.
            </p>
            <button
              onClick={handleEvilStart}
              disabled={loading}
              className="bg-purple-600 text-white px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Evil Start
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function AdminPanel({ data, onRefresh }) {
  const [activeTab, setActiveTab] = useState('bones')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)

  // Bones form
  const [boneUserId, setBoneUserId] = useState('')
  const [boneDisplayName, setBoneDisplayName] = useState('')
  const [boneAmount, setBoneAmount] = useState('')
  const [boneReason, setBoneReason] = useState('')

  // Prize form
  const [prizeName, setPrizeName] = useState('')
  const [prizeCost, setPrizeCost] = useState('')
  const [prizeStock, setPrizeStock] = useState('')
  const [prizeDesc, setPrizeDesc] = useState('')

  // Prize editing
  const [editingPrize, setEditingPrize] = useState(null)
  const [editForm, setEditForm] = useState({})

  // Admin form
  const [adminUserId, setAdminUserId] = useState('')
  const [adminDisplayName, setAdminDisplayName] = useState('')
  const [rumbleAdmins, setRumbleAdmins] = useState([])

  // Redemption history (admin-only)
  const [redemptions, setRedemptions] = useState([])
  const [redemptionsLoading, setRedemptionsLoading] = useState(false)

  useEffect(() => {
    if (activeTab === 'admins') {
      get('/api/rumble/admin/admins')
        .then((d) => setRumbleAdmins(d.admins || []))
        .catch(() => {})
    }
    if (activeTab === 'redemptions') {
      setRedemptionsLoading(true)
      get('/api/rumble/admin/redemptions')
        .then((d) => setRedemptions(d.redemptions || []))
        .catch(() => setRedemptions([]))
        .finally(() => setRedemptionsLoading(false))
    }
  }, [activeTab])

  const flash = (msg, isError = false) => {
    setMessage({ text: msg, error: isError })
    setTimeout(() => setMessage(null), 3000)
  }

  const handleAdjustBones = async (e) => {
    e.preventDefault()
    if (!boneUserId || !boneAmount) return
    setLoading(true)
    try {
      const res = await post('/api/rumble/admin/bones', {
        discord_user_id: boneUserId,
        amount: parseInt(boneAmount),
        reason: boneReason || 'Manual adjustment',
        display_name: boneDisplayName || undefined,
      })
      flash(`Bones adjusted. New balance: ${res.new_balance}`)
      setBoneUserId('')
      setBoneDisplayName('')
      setBoneAmount('')
      setBoneReason('')
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateEarning = async (key, bones) => {
    try {
      await put('/api/rumble/admin/earnings', { key, bones: parseInt(bones) })
      flash('Earning updated')
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const handleAddPrize = async (e) => {
    e.preventDefault()
    if (!prizeName) return
    setLoading(true)
    try {
      await post('/api/rumble/admin/prizes', {
        name: prizeName,
        cost: prizeCost ? parseInt(prizeCost) : 0,
        stock: prizeStock ? parseInt(prizeStock) : null,
        description: prizeDesc || null,
      })
      flash('Prize added')
      setPrizeName('')
      setPrizeCost('')
      setPrizeStock('')
      setPrizeDesc('')
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    } finally {
      setLoading(false)
    }
  }

  const handleUpdatePrize = async (id, updates) => {
    try {
      await put(`/api/rumble/admin/prizes/${id}`, updates)
      flash('Prize updated')
      setEditingPrize(null)
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const handleDeletePrize = async (id) => {
    if (!confirm('Delete this prize?')) return
    try {
      await del(`/api/rumble/admin/prizes/${id}`)
      flash('Prize deleted')
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const handleReorder = async (prizeIndex, direction) => {
    const prizes = data.prizes
    const targetIndex = prizeIndex + direction
    if (targetIndex < 0 || targetIndex >= prizes.length) return
    try {
      await post('/api/rumble/admin/prizes/reorder', {
        prize_id_a: prizes[prizeIndex].id,
        prize_id_b: prizes[targetIndex].id,
      })
      onRefresh()
    } catch (err) {
      flash(err.message, true)
    }
  }

  const startEditing = (prize) => {
    setEditingPrize(prize.id)
    setEditForm({
      name: prize.name,
      cost: prize.cost,
      stock: prize.stock ?? '',
      description: prize.description || '',
    })
  }

  const saveEditing = (id) => {
    handleUpdatePrize(id, {
      name: editForm.name,
      cost: parseInt(editForm.cost) || 0,
      stock: editForm.stock === '' ? null : parseInt(editForm.stock),
      description: editForm.description || null,
    })
  }

  const handleAddAdmin = async (e) => {
    e.preventDefault()
    if (!adminUserId) return
    setLoading(true)
    try {
      await post('/api/rumble/admin/admins', {
        discord_user_id: adminUserId,
        display_name: adminDisplayName || undefined,
      })
      flash('Admin added')
      setAdminUserId('')
      setAdminDisplayName('')
      const d = await get('/api/rumble/admin/admins')
      setRumbleAdmins(d.admins || [])
    } catch (err) {
      flash(err.message, true)
    } finally {
      setLoading(false)
    }
  }

  const handleRemoveAdmin = async (id) => {
    if (!confirm('Remove this rumble admin?')) return
    try {
      await del(`/api/rumble/admin/admins/${id}`)
      flash('Admin removed')
      const d = await get('/api/rumble/admin/admins')
      setRumbleAdmins(d.admins || [])
    } catch (err) {
      flash(err.message, true)
    }
  }

  const tabs = [
    { id: 'bones', label: 'Bones' },
    { id: 'earnings', label: 'Earnings' },
    { id: 'prizes', label: 'Prizes' },
    { id: 'redemptions', label: 'Redemptions' },
    { id: 'admins', label: 'Admins' },
  ]

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h2 className="text-base font-semibold text-text-primary mb-3">Rumble Admin</h2>

      {message && (
        <div className={`mb-3 p-2 rounded text-sm ${message.error ? 'bg-accent-red/20 text-accent-red' : 'bg-accent-green/20 text-accent-green'}`}>
          {message.text}
        </div>
      )}

      <div className="flex gap-2 mb-4 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`pb-2 px-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === t.id
                ? 'border-secondary text-secondary'
                : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Bones Tab */}
      {activeTab === 'bones' && (
        <form onSubmit={handleAdjustBones} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input
              type="text"
              placeholder="Discord User ID"
              value={boneUserId}
              onChange={(e) => setBoneUserId(e.target.value)}
              className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              required
            />
            <input
              type="text"
              placeholder="Display Name (optional)"
              value={boneDisplayName}
              onChange={(e) => setBoneDisplayName(e.target.value)}
              className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
            />
            <input
              type="number"
              placeholder="Amount (+/-)"
              value={boneAmount}
              onChange={(e) => setBoneAmount(e.target.value)}
              className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              required
            />
            <input
              type="text"
              placeholder="Reason"
              value={boneReason}
              onChange={(e) => setBoneReason(e.target.value)}
              className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="bg-secondary text-black px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            Adjust Bones
          </button>
        </form>
      )}

      {/* Earnings Tab */}
      {activeTab === 'earnings' && (
        <div className="space-y-2">
          {data.earnings?.map((e) => (
            <div key={e.key} className="flex items-center gap-3 text-sm">
              <span className="flex-1">{e.label}</span>
              <input
                type="number"
                defaultValue={e.bones}
                className="w-20 bg-bg-primary border border-border rounded px-2 py-1 text-sm text-center"
                onBlur={(ev) => {
                  const val = parseInt(ev.target.value)
                  if (!isNaN(val) && val !== e.bones) handleUpdateEarning(e.key, val)
                }}
                onKeyDown={(ev) => {
                  if (ev.key === 'Enter') ev.target.blur()
                }}
              />
              <span className="text-text-muted w-12">bones</span>
            </div>
          ))}
        </div>
      )}

      {/* Prizes Tab */}
      {activeTab === 'prizes' && (
        <div className="space-y-4">
          {/* Existing prizes */}
          {data.prizes?.map((p, idx) => (
            <div key={p.id} className="border-b border-border/50 pb-2">
              {editingPrize === p.id ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      placeholder="Name"
                      className="bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                    />
                    <input
                      type="number"
                      value={editForm.cost}
                      onChange={(e) => setEditForm({ ...editForm, cost: e.target.value })}
                      placeholder="Cost"
                      className="bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                    />
                    <input
                      type="number"
                      value={editForm.stock}
                      onChange={(e) => setEditForm({ ...editForm, stock: e.target.value })}
                      placeholder="Stock (empty = unlimited)"
                      className="bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                    />
                    <input
                      type="text"
                      value={editForm.description}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      placeholder="Description"
                      className="bg-bg-primary border border-border rounded px-2 py-1 text-sm"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveEditing(p.id)}
                      className="bg-secondary text-black px-3 py-1 rounded text-xs font-medium hover:opacity-90"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingPrize(null)}
                      className="text-text-muted hover:text-text-primary text-xs px-3 py-1"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-sm">
                  {/* Reorder buttons */}
                  <div className="flex flex-col">
                    <button
                      onClick={() => handleReorder(idx, -1)}
                      disabled={idx === 0}
                      className="text-text-muted hover:text-text-primary disabled:opacity-30 text-xs leading-none"
                      title="Move up"
                    >
                      &#9650;
                    </button>
                    <button
                      onClick={() => handleReorder(idx, 1)}
                      disabled={idx === data.prizes.length - 1}
                      className="text-text-muted hover:text-text-primary disabled:opacity-30 text-xs leading-none"
                      title="Move down"
                    >
                      &#9660;
                    </button>
                  </div>
                  <span className="flex-1 font-medium">{p.name}</span>
                  <span className="text-text-muted text-xs w-16 text-center">
                    {p.cost > 0 ? `${p.cost}b` : 'TBD'}
                  </span>
                  <span className="text-text-muted text-xs w-16 text-center">
                    {p.stock != null ? `${p.stock} left` : 'Unlim'}
                  </span>
                  <button
                    onClick={() => startEditing(p)}
                    className="text-secondary hover:text-secondary/80 text-xs px-2"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeletePrize(p.id)}
                    className="text-accent-red hover:text-accent-red/80 text-xs px-2"
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
          ))}

          {/* Add new prize */}
          <form onSubmit={handleAddPrize} className="space-y-2 pt-2 border-t border-border">
            <p className="text-xs text-text-muted font-semibold uppercase">Add Prize</p>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                placeholder="Prize Name"
                value={prizeName}
                onChange={(e) => setPrizeName(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
                required
              />
              <input
                type="number"
                placeholder="Cost (0 = TBD)"
                value={prizeCost}
                onChange={(e) => setPrizeCost(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
              <input
                type="number"
                placeholder="Stock (empty = unlimited)"
                value={prizeStock}
                onChange={(e) => setPrizeStock(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
              <input
                type="text"
                placeholder="Description"
                value={prizeDesc}
                onChange={(e) => setPrizeDesc(e.target.value)}
                className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="bg-secondary text-black px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Add Prize
            </button>
          </form>
        </div>
      )}

      {/* Redemptions Tab */}
      {activeTab === 'redemptions' && (
        redemptionsLoading
          ? <p className="text-sm text-text-muted py-2">Loading…</p>
          : <RedemptionHistory redemptions={redemptions} />
      )}

      {/* Admins Tab */}
      {activeTab === 'admins' && (
        <div className="space-y-3">
          {rumbleAdmins.map((a) => (
            <div key={a.discord_user_id} className="flex items-center justify-between text-sm border-b border-border/50 pb-2">
              <span>{a.display_name || a.discord_user_id}</span>
              <button
                onClick={() => handleRemoveAdmin(a.discord_user_id)}
                className="text-accent-red hover:text-accent-red/80 text-xs px-2"
              >
                Remove
              </button>
            </div>
          ))}
          <form onSubmit={handleAddAdmin} className="flex gap-2 pt-2 border-t border-border">
            <input
              type="text"
              placeholder="Discord User ID"
              value={adminUserId}
              onChange={(e) => setAdminUserId(e.target.value)}
              className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm flex-1"
              required
            />
            <input
              type="text"
              placeholder="Display Name"
              value={adminDisplayName}
              onChange={(e) => setAdminDisplayName(e.target.value)}
              className="bg-bg-primary border border-border rounded px-3 py-1.5 text-sm flex-1"
            />
            <button
              type="submit"
              disabled={loading}
              className="bg-secondary text-black px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Add
            </button>
          </form>
        </div>
      )}
    </div>
  )
}

export default function Rumble() {
  usePageTitle('Rumble')
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [redeemMessage, setRedeemMessage] = useState(null)
  const [editingPlayer, setEditingPlayer] = useState(null)
  const [editingBone, setEditingBone] = useState(null)

  const fetchData = useCallback(() => {
    get('/api/rumble')
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  const { standings, matches, total_matches } = data
  const isRumbleAdmin = user && (user.is_admin || user.is_rumble_admin)

  // Find user's bone balance
  const userId = user ? user.user_id : null
  const userBoneEntry = userId ? data.bones?.find((b) => b.discord_user_id === String(userId)) : null
  const userBones = userBoneEntry ? userBoneEntry.balance : (userId ? 0 : null)

  const handleRedeem = async (prizeId, prizeName, cost) => {
    if (!confirm(`Redeem "${prizeName}" for ${cost} bone${cost !== 1 ? 's' : ''}?`)) return
    try {
      const res = await post(`/api/rumble/redeem/${prizeId}`)
      setRedeemMessage({ text: `Redeemed "${res.prize_name}"! New balance: ${res.new_balance}`, error: false })
      fetchData()
    } catch (err) {
      setRedeemMessage({ text: err.message, error: true })
    }
    setTimeout(() => setRedeemMessage(null), 4000)
  }

  const handleEditPlayer = async (userId, updates) => {
    try {
      await put(`/api/rumble/admin/standings/${userId}`, updates)
      setEditingPlayer(null)
      fetchData()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDeletePlayer = async (userId) => {
    try {
      await del(`/api/rumble/admin/standings/${userId}`)
      setEditingPlayer(null)
      fetchData()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleEditBone = async (discordUserId, updates) => {
    try {
      await put(`/api/rumble/admin/bones/${discordUserId}`, updates)
      setEditingBone(null)
      fetchData()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDeleteBone = async (discordUserId) => {
    try {
      await del(`/api/rumble/admin/bones/${discordUserId}`)
      setEditingBone(null)
      fetchData()
    } catch (err) {
      alert(err.message)
    }
  }

  return (
    <div className="space-y-6">
      <div className="text-center py-6">
        <h1 className="text-3xl font-display text-secondary">Rumble</h1>
        <p className="text-text-muted mt-1">
          {total_matches} match{total_matches !== 1 ? 'es' : ''} played
        </p>
      </div>

      {redeemMessage && (
        <div className={`p-3 rounded text-sm text-center ${redeemMessage.error ? 'bg-accent-red/20 text-accent-red' : 'bg-accent-green/20 text-accent-green'}`}>
          {redeemMessage.text}
        </div>
      )}

      {/* Prize Wall & Earnings */}
      <PrizeWall
        prizes={data.prizes}
        earnings={data.earnings}
        userBones={userBones}
        userId={userId}
        onRedeem={handleRedeem}
      />

      {/* Bone Balances */}
      <BonesLeaderboard bones={data.bones} isAdmin={isRumbleAdmin} onEdit={setEditingBone} />

      {/* Standings */}
      {standings?.length > 0 && (
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-base font-semibold text-text-primary mb-3">Player Records</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-1.5 px-2 text-text-muted font-semibold w-8">#</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Player</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">W</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">L</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Games</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Win %</th>
                </tr>
              </thead>
              <tbody>
                {standings.map((p, i) => {
                  const total = p.wins + p.losses
                  const pct = total > 0 ? Math.round((p.wins / total) * 100) : 0
                  return (
                    <tr key={p.user_id} className="border-b border-border/50">
                      <td className="py-1.5 px-2 text-text-muted">{i + 1}</td>
                      <td className="py-1.5 px-2 font-medium">
                        {p.display_name || 'Unknown'}
                        {isRumbleAdmin && (
                          <button
                            onClick={() => setEditingPlayer(p)}
                            className="ml-1.5 text-text-muted hover:text-secondary inline-block align-middle"
                            title="Edit player"
                          >
                            &#9998;
                          </button>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-accent-green">{p.wins}</td>
                      <td className="py-1.5 px-2 text-accent-red">{p.losses}</td>
                      <td className="py-1.5 px-2">{total}</td>
                      <td className="py-1.5 px-2">{pct}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent Matches */}
      {matches?.length > 0 && (
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-base font-semibold text-text-primary mb-3">Recent Matches</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Winner</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Loser</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Time</th>
                  <th className="py-1.5 px-2 text-text-muted font-semibold">Date</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m) => (
                  <tr key={m.match_id} className="border-b border-border/50">
                    <td className="py-1.5 px-2 text-accent-green">{m.winner}</td>
                    <td className="py-1.5 px-2 text-accent-red">{m.loser}</td>
                    <td className="py-1.5 px-2 text-text-muted">
                      {m.match_time > 0 ? `${m.match_time} min` : '-'}
                    </td>
                    <td className="py-1.5 px-2 text-text-muted">
                      {m.timestamp ? new Date(m.timestamp).toLocaleDateString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!standings?.length && !matches?.length && !data.bones?.length && (
        <p className="text-center text-text-muted py-8">No rumble data yet.</p>
      )}

      {/* Fart Game Admin */}
      {isRumbleAdmin && <FartAdmin data={data} onRefresh={fetchData} />}

      {/* Admin Panel */}
      {isRumbleAdmin && <AdminPanel data={data} onRefresh={fetchData} />}

      {/* Edit Player Modal */}
      {editingPlayer && (
        <EditPlayerModal
          player={editingPlayer}
          onClose={() => setEditingPlayer(null)}
          onSave={handleEditPlayer}
          onDelete={handleDeletePlayer}
        />
      )}

      {/* Edit Bone Modal */}
      {editingBone && (
        <EditBoneModal
          entry={editingBone}
          onClose={() => setEditingBone(null)}
          onSave={handleEditBone}
          onDelete={handleDeleteBone}
        />
      )}
    </div>
  )
}
