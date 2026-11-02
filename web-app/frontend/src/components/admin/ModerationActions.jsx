import { useState } from 'react'
import { post } from '@/api/client'

// Same choices as the bot's DM (discord-bot/cogs/moderation_alerts.py).
// Discord caps a timeout at 28 days.
export const TIMEOUT_CHOICES = [
  { minutes: 60, label: '1 hour' },
  { minutes: 1440, label: '1 day' },
  { minutes: 10080, label: '1 week' },
  { minutes: 40320, label: '28 days' },
]
const DEFAULT_MINUTES = 1440

// Same as the bot's !ban (discord-bot/repositories/pairing_bans_repo.py).
export const PAIRING_CHOICES = [
  { key: '24h', label: '24 hours' },
  { key: '48h', label: '48 hours' },
  { key: '72h', label: '72 hours' },
  { key: 'lifetime', label: 'Lifetime' },
]

const TITLES = { timeout: 'Time out', ban: 'Ban', pairing_block: 'Block from pairing' }
const CONFIRM = { timeout: 'Confirm timeout', ban: 'Confirm ban', pairing_block: 'Confirm pairing block' }
const BLURBS = {
  timeout: "They can't chat, react or join voice in the Summit Discord until it ends.",
  ban: 'This bans them from the Summit Discord.',
  pairing_block: "They can't join the LFG queue, the website queue or challenges until it ends. The bot DMs them the reason.",
}

function durationLabel(minutes) {
  return TIMEOUT_CHOICES.find(c => c.minutes === minutes)?.label ?? `${minutes} minutes`
}

function formatDate(value) {
  if (!value) return ''
  const d = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function moderationSummary(m) {
  if (!m) return null
  const what = m.action === 'ban'
    ? 'Banned'
    : m.action === 'pairing_block'
      ? `Pairing block ${m.duration_label ?? ''}`.trim()
      : `Timed out ${durationLabel(m.duration_minutes)}`
  const who = m.by_name ? ` by ${m.by_name}` : ''
  const where = m.via === 'discord' ? ' (Discord)' : ''
  return `${what}${who}${where}, ${formatDate(m.created_at)}`
}

function ConfirmDialog({ action, userName, userId, defaultReason, onCancel, onConfirm, busy, error }) {
  const [minutes, setMinutes] = useState(DEFAULT_MINUTES)
  const [duration, setDuration] = useState('24h')
  const [reason, setReason] = useState(defaultReason ?? '')
  const isPairing = action === 'pairing_block'
  const needsReason = isPairing && reason.trim().length < 3

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="moderation-dialog-title"
    >
      <div className="w-full max-w-md bg-bg-raised border border-border rounded-lg p-5 space-y-4 shadow-xl">
        <div className="space-y-1">
          <h3 id="moderation-dialog-title" className="text-base font-semibold text-text-primary">
            {TITLES[action]} {userName}?
          </h3>
          <p className="text-sm text-text-muted">{BLURBS[action]}</p>
          <p className="text-xs text-text-muted font-mono">{userId}</p>
        </div>

        {isPairing && (
          <label className="block space-y-1">
            <span className="text-xs text-text-muted">How long</span>
            <select
              value={duration}
              onChange={e => setDuration(e.target.value)}
              className="w-full bg-bg-elevated border border-border rounded px-2 py-1.5 text-sm text-text-primary"
            >
              {PAIRING_CHOICES.map(c => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </label>
        )}

        {action === 'timeout' && (
          <label className="block space-y-1">
            <span className="text-xs text-text-muted">How long</span>
            <select
              value={minutes}
              onChange={e => setMinutes(Number(e.target.value))}
              className="w-full bg-bg-elevated border border-border rounded px-2 py-1.5 text-sm text-text-primary"
            >
              {TIMEOUT_CHOICES.map(c => (
                <option key={c.minutes} value={c.minutes}>{c.label}</option>
              ))}
            </select>
          </label>
        )}

        <label className="block space-y-1">
          <span className="text-xs text-text-muted">
            {isPairing ? 'Reason (sent to the player)' : 'Reason (shows in the Discord audit log)'}
          </span>
          <textarea
            value={reason}
            onChange={e => setReason(e.target.value)}
            maxLength={isPairing ? 1000 : 400}
            rows={2}
            className="w-full bg-bg-elevated border border-border rounded px-2 py-1.5 text-sm text-text-primary"
          />
        </label>

        {error && <p className="text-sm text-accent-red">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="px-3 py-1.5 text-sm border border-border rounded hover:bg-bg-elevated disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm({
              minutes: action === 'timeout' ? minutes : undefined,
              duration: isPairing ? duration : undefined,
              reason,
            })}
            disabled={busy || needsReason}
            className="px-3 py-1.5 text-sm rounded bg-accent-red text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy ? 'Working...' : CONFIRM[action]}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Timeout / Ban (Discord) and Pairing Block (!ban) buttons for a blocked or
 * reported player, each with a confirm dialog. Shows the last action taken (from the website or the bot's DM).
 */
export default function ModerationActions({
  userId,
  userName,
  canModerate,
  moderation,
  sourceKind,
  sourceRef,
  defaultReason,
  playerReason,
}) {
  const [current, setCurrent] = useState(moderation ?? null)
  const [pending, setPending] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const close = () => { setPending(null); setError(null) }

  const confirm = ({ minutes, duration, reason }) => {
    setBusy(true)
    setError(null)
    post('/api/admin/moderation', {
      action: pending,
      user_id: userId,
      minutes,
      duration,
      reason,
      source_kind: sourceKind,
      source_ref: sourceRef,
      confirm: true,
    })
      .then(d => {
        setCurrent(d.moderation ?? { action: pending, duration_minutes: minutes })
        setPending(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setBusy(false))
  }

  const summary = moderationSummary(current)

  return (
    <div className="space-y-1.5 min-w-[200px]">
      {canModerate ? (
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setPending('timeout')}
            className="px-2 py-1 text-xs border border-border rounded hover:bg-bg-elevated text-text-primary"
          >
            Timeout
          </button>
          <button
            onClick={() => setPending('ban')}
            className="px-2 py-1 text-xs rounded bg-accent-red text-white hover:opacity-90"
          >
            Ban
          </button>
          <button
            onClick={() => setPending('pairing_block')}
            className="px-2 py-1 text-xs border border-border rounded hover:bg-bg-elevated text-text-primary whitespace-nowrap"
          >
            Pairing Block
          </button>
        </div>
      ) : (
        <span className="text-xs text-text-muted opacity-70">No Discord account</span>
      )}
      {summary && <div className="text-xs text-text-muted">{summary}</div>}
      {pending && (
        <ConfirmDialog
          action={pending}
          userId={userId}
          userName={userName}
          defaultReason={pending === 'pairing_block' ? (playerReason ?? '') : defaultReason}
          busy={busy}
          error={error}
          onCancel={close}
          onConfirm={confirm}
        />
      )}
    </div>
  )
}
