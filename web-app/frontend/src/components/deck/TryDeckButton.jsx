import { useCallback, useState } from 'react'
import { createPsoTable } from '@/api/decks'

/**
 * "Try this Deck" — opens a Play Sorcery Online table with the deck preloaded.
 *
 * The tab is opened synchronously on click (before the request) so popup
 * blockers treat it as user-initiated; the table URL is swapped in once
 * Sorcery Online answers. If the browser blocked the tab anyway, the button
 * turns into a plain link the visitor can click.
 */
export default function TryDeckButton({ deckId, className = '', size = 'md' }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [tableUrl, setTableUrl] = useState(null)

  const sizeClasses = size === 'sm'
    ? 'text-xs px-2.5 py-1'
    : 'text-sm px-4 py-2'
  const baseClasses = `inline-flex items-center gap-1 rounded transition-colors whitespace-nowrap ${sizeClasses}`

  const launch = useCallback(async (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (busy) return
    setBusy(true)
    setError(null)

    const tab = window.open('', '_blank')
    try {
      const { game_url: gameUrl } = await createPsoTable(deckId)
      if (!gameUrl) throw new Error('No table link came back.')
      navigator.sendBeacon?.(
        '/api/analytics/banner-click',
        new Blob([JSON.stringify({ banner_type: 'pso_try_deck' })], { type: 'application/json' }),
      )
      if (tab && !tab.closed) {
        tab.location.replace(gameUrl)
      } else {
        setTableUrl(gameUrl)
      }
    } catch (err) {
      if (tab && !tab.closed) tab.close()
      setError(err.message || 'Could not open a table.')
    } finally {
      setBusy(false)
    }
  }, [busy, deckId])

  if (tableUrl) {
    return (
      <a
        href={tableUrl}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className={`${baseClasses} bg-secondary hover:bg-secondary/80 text-black font-medium ${className}`}
      >
        Open your table ↗
      </a>
    )
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={launch}
        disabled={busy}
        title="Opens a Play Sorcery Online table with this deck already loaded"
        className={`${baseClasses} bg-secondary hover:bg-secondary/80 text-black font-medium disabled:opacity-60 disabled:cursor-wait ${className}`}
      >
        {busy ? 'Opening table...' : 'Try this Deck ↗'}
      </button>
      {error && <span className="text-xs text-accent-red max-w-[16rem] text-right">{error}</span>}
    </span>
  )
}
