import { useCallback, useEffect, useState } from 'react'
import { isEuropeanVisitor } from '@/utils/region'

// Cardmarket has no link that pre-fills a wants list, so the button copies
// the deck in Cardmarket's paste format ("2 Card Name", one per line) and
// opens the Sorcery wants page, where the visitor pastes it into a list.
export const CARDMARKET_WANTS_URL = 'https://www.cardmarket.com/en/Sorcery/Wants'

export function cardmarketDeckList(cards) {
  return (cards || [])
    .filter((c) => c?.name && c.qty > 0)
    .map((c) => `${c.qty} ${c.name}`)
    .join('\n')
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Older browsers / non-secure context: hidden textarea fallback
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch { /* ignore */ }
    area.remove()
    return ok
  }
}

/** "Buy on Cardmarket" — shown only to visitors in Europe. */
export default function CardmarketButton({ cards }) {
  const [europe, setEurope] = useState(false)
  const [copied, setCopied] = useState(null)
  const deckList = cardmarketDeckList(cards)

  useEffect(() => {
    let alive = true
    isEuropeanVisitor().then((v) => { if (alive) setEurope(v) })
    return () => { alive = false }
  }, [])

  const handleClick = useCallback(async () => {
    // Open the tab synchronously so popup blockers allow it
    window.open(CARDMARKET_WANTS_URL, '_blank', 'noopener,noreferrer')
    navigator.sendBeacon?.('/api/analytics/banner-click',
      new Blob([JSON.stringify({ banner_type: 'cardmarket_buy' })], { type: 'application/json' }))
    setCopied(await copyText(deckList))
  }, [deckList])

  if (!europe || !deckList) return null

  return (
    <div className="relative">
      <button
        type="button"
        onClick={handleClick}
        className="inline-flex items-center gap-1 bg-[#012d5a] hover:bg-[#023f7d] text-white text-sm px-4 py-2 rounded transition-colors whitespace-nowrap"
      >
        Buy on Cardmarket ↗
      </button>
      {copied !== null && (
        <div className="absolute left-0 sm:left-auto sm:right-0 mt-2 z-20 w-72 max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-bg-raised p-3 text-xs text-text-muted shadow-lg">
          {copied ? (
            <p className="text-text-primary font-medium mb-1">Deck list copied.</p>
          ) : (
            <p className="text-text-primary font-medium mb-1">Copy this deck list:</p>
          )}
          {!copied && (
            <textarea
              readOnly
              value={deckList}
              onFocus={(e) => e.target.select()}
              className="w-full h-24 mb-2 bg-bg-base border border-border rounded p-1 font-mono text-[11px] text-text-primary"
            />
          )}
          <p>
            On Cardmarket, open or create a wants list, paste the list into the
            box and press <span className="text-text-primary">Add</span>. Then use
            Shopping Wizard to buy it.
          </p>
          <button
            type="button"
            onClick={() => setCopied(null)}
            className="mt-2 text-secondary hover:underline"
          >
            Got it
          </button>
        </div>
      )}
    </div>
  )
}
