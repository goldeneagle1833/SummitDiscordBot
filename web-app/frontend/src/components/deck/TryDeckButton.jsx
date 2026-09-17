import { useCallback, useState } from 'react'
import { createPsoTable } from '@/api/decks'

/**
 * "Try this Deck" — opens a Play Sorcery Online table with the deck preloaded.
 *
 * Sorcery Online tables always seat two, so the visitor takes the seat holding
 * the deck and the other seat stays open; its link is offered as an invite.
 *
 * The tab is opened synchronously on click (before the request) so popup
 * blockers treat it as user-initiated, and the table URL is swapped in once
 * Sorcery Online answers. If the browser blocked the tab anyway, the button
 * turns into a plain link the visitor can click.
 */
export default function TryDeckButton({ deckId, className = '', size = 'md' }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [table, setTable] = useState(null)
  const [copied, setCopied] = useState(false)

  const sizeClasses = size === 'sm'
    ? 'text-xs px-2.5 py-1'
    : 'text-sm px-4 py-2'
  const baseClasses = `inline-flex items-center gap-1 rounded transition-colors whitespace-nowrap ${sizeClasses}`
  const primaryClasses = `${baseClasses} bg-secondary hover:bg-secondary/80 text-black font-medium`

  const launch = useCallback(async (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (busy) return
    setBusy(true)
    setError(null)

    const tab = window.open('', '_blank')
    try {
      const { game_url: gameUrl, invite_url: inviteUrl } = await createPsoTable(deckId)
      if (!gameUrl) throw new Error('No table link came back.')
      navigator.sendBeacon?.(
        '/api/analytics/banner-click',
        new Blob([JSON.stringify({ banner_type: 'pso_try_deck' })], { type: 'application/json' }),
      )
      const opened = Boolean(tab) && !tab.closed
      if (opened) tab.location.replace(gameUrl)
      setTable({ gameUrl, inviteUrl, opened })
    } catch (err) {
      if (tab && !tab.closed) tab.close()
      setError(err.message || 'Could not open a table.')
    } finally {
      setBusy(false)
    }
  }, [busy, deckId])

  const copyInvite = useCallback(async (e) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(table.inviteUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard blocked (insecure context, denied permission) — the link is
      // still shown, so the visitor can copy it by hand.
      setCopied(false)
    }
  }, [table])

  if (table) {
    return (
      <span className="inline-flex flex-col items-end gap-1">
        {!table.opened && (
          <a
            href={table.gameUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className={`${primaryClasses} ${className}`}
          >
            Open your table ↗
          </a>
        )}
        {table.inviteUrl && (
          <button
            type="button"
            onClick={copyInvite}
            title={table.inviteUrl}
            className={`${baseClasses} border border-border text-text-muted hover:text-secondary`}
          >
            {copied ? 'Invite link copied' : 'Copy invite link'}
          </button>
        )}
      </span>
    )
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={launch}
        disabled={busy}
        aria-label="Try this Deck"
        title="Opens a Play Sorcery Online table with this deck already loaded"
        className={`${primaryClasses} disabled:opacity-60 disabled:cursor-wait ${className}`}
      >
        {busy ? 'Opening table...' : 'Try this Deck ↗'}
      </button>
      {error && <span className="text-xs text-accent-red max-w-[16rem] text-right">{error}</span>}
    </span>
  )
}
