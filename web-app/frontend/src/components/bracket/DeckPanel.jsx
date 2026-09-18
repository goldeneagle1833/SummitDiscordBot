import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getBracketDeck,
  submitBracketDeck,
  adminSubmitBracketDeck,
  adminDeleteBracketDeck,
} from '@/api/brackets'
import DeckVisualizer from '@/components/deck/DeckVisualizer'
import Spinner from '@/components/ui/Spinner'
import { avatarUrl } from '@/utils/avatar'

const INPUT = 'w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm'

function StatusTag({ player }) {
  if (!player.has_deck) {
    return <span className="text-xs text-text-muted">No deck yet</span>
  }
  if (player.deck_visible) {
    return <span className="text-xs text-accent-green">Deck revealed</span>
  }
  return (
    <span className="text-xs text-text-muted" title="Revealed once they are knocked out">
      Submitted · hidden
    </span>
  )
}

/** The deck itself, fetched only when someone opens it. */
function DeckDetail({ slug, seed }) {
  const [state, setState] = useState({ loading: true, deck: null, error: null })

  useEffect(() => {
    let active = true
    setState({ loading: true, deck: null, error: null })
    getBracketDeck(slug, seed)
      .then((res) => active && setState({ loading: false, deck: res.deck, error: null }))
      .catch((e) => active && setState({ loading: false, deck: null, error: e.message }))
    return () => {
      active = false
    }
  }, [slug, seed])

  if (state.loading) return <Spinner />
  if (state.error) return <p className="text-sm text-accent-red">{state.error}</p>

  const deck = state.deck || {}
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        {deck.name && <span className="font-medium">{deck.name}</span>}
        {deck.avatar?.[0]?.name && (
          <span className="text-text-muted">{deck.avatar[0].name}</span>
        )}
      </div>
      <DeckVisualizer spellbook={deck.spellbook} atlas={deck.atlas} sideboard={deck.sideboard} />
    </div>
  )
}

function SubmitForm({ slug, seed, isAdmin, onDone }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (isAdmin) {
        await adminSubmitBracketDeck(slug, seed, url.trim())
      } else {
        await submitBracketDeck(slug, url.trim())
      }
      setUrl('')
      await onDone()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap gap-2 items-start">
      <input
        className={`${INPUT} py-1 flex-1 min-w-[16rem]`}
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste your deck link"
        aria-label={isAdmin ? `Deck link for seed ${seed}` : 'Your deck link'}
        required
      />
      <button
        type="submit"
        disabled={busy}
        className="px-3 py-1 rounded bg-secondary text-black text-sm font-medium disabled:opacity-50"
      >
        {busy ? 'Saving…' : 'Save deck'}
      </button>
      {error && <p className="w-full text-sm text-accent-red">{error}</p>}
    </form>
  )
}

/**
 * The decklists for a bracket.
 *
 * A deck is hidden from everyone but its owner (and admins) until that player
 * is knocked out, so nobody can scout an opponent they have still to play.
 */
export default function DeckPanel({ slug, roster, isAdmin = false, onChanged }) {
  const [open, setOpen] = useState(null)
  const [adding, setAdding] = useState(null)

  if (!roster) return null

  const players = roster.players || []
  const mine = players.find((p) => p.can_submit)

  return (
    <div className="bg-bg-surface border border-border rounded-lg">
      <div className="px-5 py-3 border-b border-border flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display">Decklists</h2>
        <p className="text-xs text-text-muted">
          {roster.submitted} of {players.length} submitted
          {roster.missing ? ` · ${roster.missing} still to come` : ''}
        </p>
      </div>

      {mine && (
        <div className="px-5 py-3 border-b border-border bg-secondary/5">
          <p className="text-sm mb-2">
            {mine.has_deck
              ? 'Your deck is saved. It stays hidden until you are knocked out.'
              : 'Submit your decklist. Nobody else sees it until you are knocked out.'}
          </p>
          <SubmitForm slug={slug} onDone={onChanged} />
        </div>
      )}

      <ul className="divide-y divide-border">
        {players.map((player) => {
          const avatar = avatarUrl(player, 32)
          const isOpen = open === player.seed

          return (
            <li key={player.seed} className="px-5 py-2.5">
              <div className="flex flex-wrap items-center gap-3">
                <span className="w-5 text-xs text-text-muted">{player.seed}</span>
                {avatar ? (
                  <img src={avatar} alt="" className="w-6 h-6 rounded-full object-cover" />
                ) : (
                  <span className="w-6 h-6 rounded-full bg-bg-elevated" />
                )}

                <span className="flex-1 min-w-0 truncate text-sm">
                  {player.user_id ? (
                    <Link
                      to={`/player/${player.user_id}`}
                      className="hover:text-primary transition-colors"
                    >
                      {player.display_name}
                    </Link>
                  ) : (
                    player.display_name
                  )}
                  {player.eliminated && (
                    <span className="text-text-muted text-xs"> · out</span>
                  )}
                </span>

                {player.avatar_name && (
                  <span className="text-xs text-text-muted hidden sm:inline">
                    {player.avatar_name}
                  </span>
                )}

                <StatusTag player={player} />

                {player.deck_visible && (
                  <button
                    onClick={() => setOpen(isOpen ? null : player.seed)}
                    className="text-xs text-secondary hover:underline"
                  >
                    {isOpen ? 'Hide' : 'View deck'}
                  </button>
                )}

                {isAdmin && (
                  <>
                    <button
                      onClick={() => setAdding(adding === player.seed ? null : player.seed)}
                      className="text-xs text-secondary hover:underline"
                    >
                      {player.has_deck ? 'Replace' : 'Add deck'}
                    </button>
                    {player.has_deck && (
                      <button
                        onClick={async () => {
                          await adminDeleteBracketDeck(slug, player.seed)
                          await onChanged()
                        }}
                        className="text-xs text-accent-red hover:underline"
                      >
                        Remove
                      </button>
                    )}
                  </>
                )}
              </div>

              {isAdmin && adding === player.seed && (
                <div className="mt-2">
                  <SubmitForm
                    slug={slug}
                    seed={player.seed}
                    isAdmin
                    onDone={async () => {
                      setAdding(null)
                      await onChanged()
                    }}
                  />
                </div>
              )}

              {isOpen && (
                <div className="mt-3 pt-3 border-t border-border">
                  {player.deck_url && (
                    <a
                      href={player.deck_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-secondary hover:underline"
                    >
                      Open on Curiosa
                    </a>
                  )}
                  <DeckDetail key={player.seed} slug={slug} seed={player.seed} />
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
