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
                                  ? 'bg-secondary text-bg-primary hover:opacity-90'
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

function BonesLeaderboard({ bones }) {
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
                <td className="py-1.5 px-2 font-medium">{b.display_name || 'Unknown'}</td>
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
  if (!redemptions?.length) return null
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4">
      <h2 className="text-base font-semibold text-text-primary mb-3">Redemption History</h2>
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

  useEffect(() => {
    if (activeTab === 'admins') {
      get('/api/rumble/admin/admins')
        .then((d) => setRumbleAdmins(d.admins || []))
        .catch(() => {})
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
            className="bg-secondary text-bg-primary px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
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
                      className="bg-secondary text-bg-primary px-3 py-1 rounded text-xs font-medium hover:opacity-90"
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
              className="bg-secondary text-bg-primary px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              Add Prize
            </button>
          </form>
        </div>
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
              className="bg-secondary text-bg-primary px-4 py-1.5 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
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
      <BonesLeaderboard bones={data.bones} />

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
                      <td className="py-1.5 px-2 font-medium">{p.display_name || 'Unknown'}</td>
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

      {/* Redemption History */}
      <RedemptionHistory redemptions={data.redemptions} />

      {!standings?.length && !matches?.length && !data.bones?.length && (
        <p className="text-center text-text-muted py-8">No rumble data yet.</p>
      )}

      {/* Admin Panel */}
      {isRumbleAdmin && <AdminPanel data={data} onRefresh={fetchData} />}
    </div>
  )
}
