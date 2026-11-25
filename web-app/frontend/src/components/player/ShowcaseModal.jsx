import { useEffect, useRef, useState } from 'react'
import { getRivalOptions, setShowcase } from '@/api/players'
import { cardImageUrl, searchArticleCards } from '@/api/articles'

export const BIO_MAX = 160
const inputCls = 'w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm focus:border-secondary/70 outline-none'

function CardSearch({ value, onChange }) {
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
        .then((d) => live && setResults(d.cards || []))
        .catch(() => live && setResults([]))
        .finally(() => live && setBusy(false))
    }, 250)
    return () => {
      live = false
      clearTimeout(t)
    }
  }, [query])

  if (value) {
    return (
      <div className="flex items-center gap-3">
        <img src={cardImageUrl(value.image)} alt="" className="w-10 h-14 object-cover rounded-sm bg-bg-raised" />
        <span className="text-sm text-text-primary flex-1 min-w-0 break-words">{value.name}</span>
        <button type="button" onClick={() => onChange(null)} className="text-xs text-accent-red hover:underline">
          Remove
        </button>
      </div>
    )
  }
  return (
    <div className="relative">
      <input
        id="showcase-card"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className={inputCls}
        placeholder="Search for a card"
        autoComplete="off"
      />
      {query.trim().length >= 2 && (
        <ul className="absolute z-20 left-0 right-0 mt-1 max-h-60 overflow-y-auto rounded border border-border bg-bg-surface shadow-lg">
          {results.map((c) => (
            <li key={c.name}>
              <button
                type="button"
                onClick={() => {
                  onChange(c)
                  setQuery('')
                }}
                className="w-full flex items-center gap-3 px-3 py-1.5 text-left text-sm hover:bg-bg-raised"
              >
                <img src={cardImageUrl(c.image)} alt="" loading="lazy" className="w-8 h-11 object-cover rounded-sm bg-bg-raised shrink-0" />
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
  )
}

/** Pick a rival from the players they have played, most games first. */
function RivalPicker({ playerId, value, onChange }) {
  const [players, setPlayers] = useState(null)
  const [query, setQuery] = useState('')
  useEffect(() => {
    let live = true
    getRivalOptions(playerId)
      .then((d) => live && setPlayers(d.players || []))
      .catch(() => live && setPlayers([]))
    return () => {
      live = false
    }
  }, [playerId])

  if (value) {
    return (
      <div className="flex items-center gap-3">
        <span className="text-sm text-text-primary flex-1 min-w-0 break-words">
          {value.name}
          <span className="text-text-muted tabular-nums"> · {value.wins}W {value.losses}L</span>
        </span>
        <button type="button" onClick={() => onChange(null)} className="text-xs text-accent-red hover:underline">
          Remove
        </button>
      </div>
    )
  }
  if (players === null) return <p className="text-sm text-text-muted">Loading players…</p>
  if (!players.length) return <p className="text-sm text-text-muted">Play a ranked game first, then pick a rival.</p>
  const q = query.trim().toLowerCase()
  const shown = (q ? players.filter((p) => p.name.toLowerCase().includes(q)) : players).slice(0, 30)
  return (
    <div className="space-y-2">
      <input
        id="showcase-rival"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className={inputCls}
        placeholder="Search players you've played"
        autoComplete="off"
      />
      <ul className="max-h-52 overflow-y-auto rounded border border-border divide-y divide-border">
        {shown.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onChange(p)}
              className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-bg-raised"
            >
              <span className="min-w-0 break-words text-text-primary">{p.name}</span>
              <span className="text-text-muted tabular-nums shrink-0">{p.wins}W {p.losses}L</span>
            </button>
          </li>
        ))}
        {!shown.length && <li className="px-3 py-2 text-sm text-text-muted">No players found.</li>}
      </ul>
    </div>
  )
}

/**
 * Owner's editor for the profile boxes: short description, favorite card and
 * rival. ``focus`` ('bio' | 'card' | 'rival') jumps to the one they tapped.
 */
export default function ShowcaseModal({ playerId, current, focus = 'bio', onClose, onSaved }) {
  const [bio, setBio] = useState(current?.bio || '')
  const [card, setCard] = useState(current?.favorite_card || null)
  const [rival, setRival] = useState(current?.rival || null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const refs = { bio: useRef(null), card: useRef(null), rival: useRef(null) }

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const el = refs[focus]?.current
    el?.scrollIntoView?.({ block: 'nearest' })
    el?.querySelector?.('input, textarea')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await setShowcase(playerId, {
        bio: bio.trim(),
        favorite_card: card?.name || null,
        rival: rival?.id || null,
      })
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1100] flex items-start sm:items-center justify-center bg-black/60 overflow-y-auto" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Profile showcase"
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4 my-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text-primary mb-1">Profile Showcase</h3>
        <p className="text-sm text-text-muted mb-5">
          Everyone who visits your profile sees these. Leave any of them empty and it won't show.
        </p>

        <div ref={refs.bio}>
          <label htmlFor="showcase-bio" className="flex justify-between text-xs text-text-muted mb-1">
            <span>Short description</span>
            <span className={bio.length > BIO_MAX - 15 ? 'text-secondary' : ''}>{bio.length}/{BIO_MAX}</span>
          </label>
          <textarea
            id="showcase-bio"
            rows={3}
            maxLength={BIO_MAX}
            value={bio}
            onChange={(e) => setBio(e.target.value.replace(/\n/g, ' '))}
            placeholder="A line or two about you as a player"
            className={`${inputCls} resize-none`}
          />
          <p className="text-xs text-text-muted mt-1">Plain text, no links.</p>
        </div>

        <div ref={refs.card} className="mt-5">
          <label htmlFor="showcase-card" className="block text-xs text-text-muted mb-1">Favorite card</label>
          <CardSearch value={card} onChange={setCard} />
        </div>

        <div ref={refs.rival} className="mt-5">
          <label htmlFor="showcase-rival" className="block text-xs text-text-muted mb-1">Rival</label>
          <RivalPicker playerId={playerId} value={rival} onChange={setRival} />
        </div>

        {error && <p className="text-xs text-accent-red mt-3">{error}</p>}
        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
