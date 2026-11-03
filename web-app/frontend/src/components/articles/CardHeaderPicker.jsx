import { useEffect, useState } from 'react'
import { cardImageUrl, searchArticleCards } from '@/api/articles'

const inputCls = 'w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm focus:border-secondary/70 outline-none'

/** Pick a Sorcery card whose art becomes the article's header image.
 *  value: { name, image } or null. */
export default function CardHeaderPicker({ value, onChange }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      return undefined
    }
    let live = true
    setBusy(true)
    const t = setTimeout(() => {
      searchArticleCards(q)
        .then((d) => { if (live) setResults(d.cards || []) })
        .catch(() => { if (live) setResults([]) })
        .finally(() => { if (live) setBusy(false) })
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [query])

  const pick = (card) => {
    onChange(card)
    setQuery('')
    setResults([])
  }

  return (
    <div className="rounded-lg border border-dashed border-border p-3 space-y-2">
      <span className="block text-sm font-medium">
        Header image <span className="text-text-muted font-normal">(optional, pick a card)</span>
      </span>
      {value ? (
        <div className="space-y-2">
          <div className="overflow-hidden rounded border border-border max-w-md">
            <img src={cardImageUrl(value.image)} alt="" className="w-full aspect-[2.4/1] object-cover object-[50%_22%] bg-bg-elevated" />
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-text-primary">{value.name}</span>
            <button type="button" onClick={() => onChange(null)} className="text-xs text-red-400 hover:underline">Remove</button>
          </div>
        </div>
      ) : (
        <div className="relative">
          <input
            aria-label="Search for a card"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className={inputCls}
            placeholder="Search for a card, e.g. Pudge Butcher"
          />
          {query.trim().length >= 2 && (
            <ul className="absolute z-20 left-0 right-0 mt-1 max-h-72 overflow-y-auto rounded border border-border bg-bg-surface shadow-lg">
              {results.map((c) => (
                <li key={c.name}>
                  <button
                    type="button"
                    onClick={() => pick(c)}
                    className="w-full flex items-center gap-3 px-3 py-1.5 text-left text-sm hover:bg-bg-elevated"
                  >
                    <img src={cardImageUrl(c.image)} alt="" loading="lazy" className="w-8 h-11 object-cover rounded-sm bg-bg-elevated shrink-0" />
                    {c.name}
                  </button>
                </li>
              ))}
              {!results.length && (
                <li className="px-3 py-2 text-sm text-text-muted">{busy ? 'Searching…' : 'No cards found.'}</li>
              )}
            </ul>
          )}
        </div>
      )}
      <p className="text-xs text-text-muted">The card's art shows at the top of your article and on its tile.</p>
    </div>
  )
}
