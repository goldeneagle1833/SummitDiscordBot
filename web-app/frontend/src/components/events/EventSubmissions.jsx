import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  submitEvent, getMySubmissions, getEventSubmissions, approveSubmission, rejectSubmission, pollEventJob,
} from '@/api/events'

const STATUS_STYLE = {
  pending: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/40',
  importing: 'bg-blue-500/15 text-blue-300 border-blue-500/40',
  approved: 'bg-green-500/15 text-green-300 border-green-500/40',
  rejected: 'bg-red-500/15 text-red-300 border-red-500/40',
  failed: 'bg-red-500/15 text-red-300 border-red-500/40',
}
const STATUS_LABEL = {
  pending: 'Waiting for approval',
  importing: 'Importing',
  approved: 'Approved',
  rejected: 'Not added',
  failed: 'Import failed',
}

function StatusChip({ status }) {
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded border font-semibold whitespace-nowrap ${STATUS_STYLE[status] || ''}`}>
      {STATUS_LABEL[status] || status}
    </span>
  )
}

function Modal({ title, onClose, children, wide = false }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`bg-bg-surface border border-border rounded-lg p-5 sm:p-6 w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} mx-4 max-h-[90vh] overflow-y-auto`}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-display text-secondary mb-4">{title}</h3>
        {children}
      </div>
    </div>
  )
}

function eventLabel(s) {
  return s.title || s.event_name || s.event_url
}

function SubmissionMeta({ s }) {
  const bits = []
  if (s.event_date) bits.push(s.event_date)
  if (s.player_count != null) bits.push(`${s.player_count} players`)
  if (s.deck_links) bits.push(`${s.deck_links} deck link${s.deck_links !== 1 ? 's' : ''}`)
  return bits.length ? <span className="text-xs text-text-muted">{bits.join(' · ')}</span> : null
}

/** What a player sees: send in an event, and how their earlier ones went. */
export function SubmitEventModal({ loggedIn, onClose, startOnMine = false, threshold = 16 }) {
  const [tab, setTab] = useState(startOnMine ? 'mine' : 'submit')
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [deckLinks, setDeckLinks] = useState('')
  const [mode, setMode] = useState('import') // 'import' (decks from the event page) or 'manual' (deck links)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(null)
  const [mine, setMine] = useState(null)

  const loadMine = useCallback(() => {
    if (!loggedIn) return
    getMySubmissions().then((d) => setMine(d.submissions || [])).catch(() => setMine([]))
  }, [loggedIn])

  useEffect(() => { loadMine() }, [loadMine])

  const send = async () => {
    setSending(true)
    setError(null)
    try {
      const deck_urls = mode === 'manual' ? deckLinks.split('\n').map((u) => u.trim()).filter(Boolean) : []
      const res = await submitEvent({ event_url: url.trim(), title: title.trim(), note: note.trim(), deck_urls })
      setSent(res.submission)
      setUrl(''); setTitle(''); setNote(''); setDeckLinks('')
      loadMine()
    } catch (e) {
      setError(e.message || 'Could not send that event')
    } finally {
      setSending(false)
    }
  }

  if (!loggedIn) {
    const next = encodeURIComponent('/top-8?submit=1')
    return (
      <Modal title="Add an event" onClose={onClose}>
        <p className="text-sm text-text-muted mb-4">
          Played in a Sorcery event on sorcerytcg.com? Send it in and, once it is approved, it goes on the
          Top 8 page and the placings show on players' Summit profiles. You need to log in first.
        </p>
        <div className="flex justify-end gap-2">
          <button className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text" onClick={onClose}>Cancel</button>
          <a href={`/auth/discord?next=${next}`} className="text-xs bg-primary text-black px-3 py-1.5 rounded font-semibold">Log in with Discord</a>
        </div>
      </Modal>
    )
  }

  const waiting = (mine || []).filter((s) => s.status === 'pending').length

  return (
    <Modal title="Add an event" onClose={onClose}>
      <div className="flex gap-1 mb-4 bg-bg-raised rounded p-0.5" role="tablist">
        {[['submit', 'Send in an event'], ['mine', `My submissions${mine?.length ? ` (${mine.length})` : ''}`]].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`flex-1 text-xs py-1.5 rounded font-semibold transition-colors ${tab === key ? 'bg-primary text-black' : 'text-text-muted hover:text-text'}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'submit' ? (
        sent ? (
          <div className="space-y-3">
            <div className="p-3 rounded border border-green-500/40 bg-green-500/10 text-sm">
              <p className="text-green-300 font-semibold mb-1">Thanks, it's in!</p>
              <p className="text-text-muted text-xs">
                The Summit team will check it before it goes live. You'll get a Discord DM when it's approved, and you can
                check on it any time under My submissions.
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <button className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text" onClick={() => setSent(null)}>Send another</button>
              <button className="text-xs bg-secondary text-black px-3 py-1.5 rounded font-semibold" onClick={() => setTab('mine')}>My submissions</button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex gap-1 mb-3 border border-border rounded p-0.5">
              {[['import', 'Import from event link'], ['manual', 'Manual deck links']].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={mode === key}
                  className={`flex-1 text-xs py-1.5 rounded font-semibold transition-colors ${mode === key ? 'bg-secondary text-black' : 'text-text-muted hover:text-text'}`}
                  onClick={() => setMode(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-text-muted/80 mb-3">
              {mode === 'import'
                ? 'The decks, standings and player count all come from the event page.'
                : "Use this when the event page has no deck lists (for example only the top 4 were collected). The player count and standings still come from the event page."}
            </p>
            <label htmlFor="submit-event-url" className="text-xs text-text-muted block mb-1">sorcerytcg.com event link</label>
            <input
              id="submit-event-url"
              type="url"
              inputMode="url"
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3"
              placeholder="https://sorcerytcg.com/events/..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <label htmlFor="submit-event-title" className="text-xs text-text-muted block mb-1">Event name (optional, we use the event's own name)</label>
            <input
              id="submit-event-title"
              type="text"
              maxLength={120}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            {mode === 'manual' && (
              <>
                <label htmlFor="submit-event-decks" className="text-xs text-text-muted block mb-1">
                  Deck links (one per line, 1st place first)
                </label>
                <textarea
                  id="submit-event-decks"
                  className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3 min-h-[96px]"
                  placeholder={'https://curiosa.io/decks/...\nhttps://curiosa.io/decks/...'}
                  value={deckLinks}
                  onChange={(e) => setDeckLinks(e.target.value)}
                />
              </>
            )}
            <label htmlFor="submit-event-note" className="text-xs text-text-muted block mb-1">Note for the Summit team (optional)</label>
            <textarea
              id="submit-event-note"
              maxLength={500}
              className="w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-3 min-h-[64px]"
              placeholder="Store, format, anything we should know"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <ul className="text-xs text-text-muted/80 mb-4 space-y-1 list-disc pl-4">
              <li>Events go live after the Summit team approves them.</li>
              <li>Events with fewer than {threshold} players are tagged <span className="text-text">Local</span>.</li>
              <li>No deck lists? The placings still go on players' Summit profiles.</li>
            </ul>
            {waiting > 0 && <p className="text-xs text-text-muted mb-3">You have {waiting} event{waiting !== 1 ? 's' : ''} waiting for approval.</p>}
            {error && <p className="text-accent-red text-xs mb-3" role="alert">{error}</p>}
            <div className="flex justify-end gap-2">
              <button className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text" onClick={onClose}>Cancel</button>
              <button
                className="text-xs bg-secondary text-black px-3 py-1.5 rounded font-semibold disabled:opacity-50"
                onClick={send}
                disabled={sending || !url.trim() || (mode === 'manual' && !deckLinks.trim())}
              >
                {sending ? 'Sending...' : 'Send for approval'}
              </button>
            </div>
          </>
        )
      ) : (
        <div className="space-y-2">
          {mine === null && <p className="text-xs text-text-muted">Loading...</p>}
          {mine?.length === 0 && <p className="text-xs text-text-muted">You haven't sent in any events yet.</p>}
          {mine?.map((s) => (
            <div key={s.id} className="p-3 rounded border border-border bg-bg-raised">
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className="text-sm font-semibold break-words min-w-0">{eventLabel(s)}</span>
                <StatusChip status={s.status} />
              </div>
              <p className="text-xs text-text-muted">{s.outcome}</p>
              {s.review_note && <p className="text-xs mt-1 border-l-2 border-secondary/50 pl-2">{s.review_note}</p>}
              {s.status === 'approved' && s.folder && (
                <Link to={`/top-8/${encodeURIComponent(s.folder)}`} className="text-xs text-secondary hover:underline mt-1 inline-block" onClick={onClose}>
                  View on the Top 8 page
                </Link>
              )}
            </div>
          ))}
          <div className="flex justify-end pt-2">
            <button className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text" onClick={onClose}>Close</button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function ReviewRow({ s, onDone }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(null)
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(s.error || null)

  const approve = async () => {
    setBusy('approve'); setError(null); setProgress('Starting...')
    try {
      const res = await approveSubmission(s.id, note.trim())
      const result = await pollEventJob(res.job_id, { onProgress: setProgress })
      if (!result?.success) setError(result?.error || 'Import failed')
      onDone()
    } catch (e) {
      setError(e.message || 'Could not approve')
    } finally {
      setBusy(null); setProgress(null)
    }
  }
  const reject = async () => {
    setBusy('reject'); setError(null)
    try {
      await rejectSubmission(s.id, note.trim())
      onDone()
    } catch (e) {
      setError(e.message || 'Could not reject')
    } finally {
      setBusy(null)
    }
  }

  const open = s.status === 'pending' || s.status === 'failed'
  const local = s.player_count != null && s.player_count < 16

  return (
    <div className="p-3 rounded border border-border bg-bg-raised">
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="min-w-0">
          <a href={s.event_url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-secondary hover:underline break-words">
            {eventLabel(s)}
          </a>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-0.5">
            <SubmissionMeta s={s} />
            {open && local && <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/10 text-text-muted">Will be tagged Local</span>}
          </div>
        </div>
        <StatusChip status={s.status} />
      </div>
      <p className="text-xs text-text-muted">Sent by <span className="text-text">{s.submitter_name || 'a player'}</span>{s.created_at ? ` on ${s.created_at.slice(0, 10)}` : ''}</p>
      {s.note && <p className="text-xs mt-1 border-l-2 border-border pl-2 break-words">{s.note}</p>}
      {!open && <p className="text-xs text-text-muted mt-1">{s.outcome}{s.reviewed_by ? ` (${s.reviewed_by})` : ''}</p>}
      {!open && s.review_note && <p className="text-xs mt-1 border-l-2 border-secondary/50 pl-2">{s.review_note}</p>}
      {error && <p className="text-accent-red text-xs mt-2" role="alert">{error}</p>}
      {open && (
        <div className="mt-2">
          <label className="sr-only" htmlFor={`review-note-${s.id}`}>Note to the player</label>
          <input
            id={`review-note-${s.id}`}
            type="text"
            maxLength={500}
            className="w-full bg-bg-surface border border-border rounded px-3 py-1.5 text-xs mb-2"
            placeholder="Note to the player (optional, sent with the DM)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={!!busy}
          />
          <div className="flex flex-wrap justify-end gap-2">
            <button
              className="text-xs px-3 py-1.5 rounded border border-red-500/50 text-red-300 hover:bg-red-500/10 disabled:opacity-50"
              onClick={reject}
              disabled={!!busy}
            >
              {busy === 'reject' ? 'Rejecting...' : 'Reject'}
            </button>
            <button
              className="text-xs bg-secondary text-black px-3 py-1.5 rounded font-semibold disabled:opacity-50"
              onClick={approve}
              disabled={!!busy}
            >
              {busy === 'approve' ? (progress || 'Importing...') : s.status === 'failed' ? 'Try again' : 'Approve & publish'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Admin list of player submissions with Approve / Reject. */
export function ReviewSubmissionsModal({ onClose, onChanged }) {
  const [filter, setFilter] = useState('open')
  const [subs, setSubs] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    getEventSubmissions()
      .then((d) => setSubs(d.submissions || []))
      .catch((e) => setError(e.message || 'Could not load submissions'))
  }, [])
  useEffect(() => { load() }, [load])

  const shown = (subs || []).filter((s) =>
    filter === 'open' ? ['pending', 'failed', 'importing'].includes(s.status) : !['pending', 'failed', 'importing'].includes(s.status))

  const refresh = () => { load(); onChanged?.() }

  return (
    <Modal title="Event submissions" onClose={onClose} wide>
      <div className="flex gap-1 mb-4 bg-bg-raised rounded p-0.5" role="tablist">
        {[['open', 'Waiting'], ['done', 'Handled']].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={filter === key}
            className={`flex-1 text-xs py-1.5 rounded font-semibold transition-colors ${filter === key ? 'bg-primary text-black' : 'text-text-muted hover:text-text'}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {error && <p className="text-accent-red text-xs mb-3">{error}</p>}
      {subs === null && !error && <p className="text-xs text-text-muted">Loading...</p>}
      {subs && shown.length === 0 && (
        <p className="text-xs text-text-muted">{filter === 'open' ? 'Nothing waiting. 🎉' : 'Nothing handled yet.'}</p>
      )}
      <div className="space-y-2">
        {shown.map((s) => <ReviewRow key={`${s.id}-${s.status}`} s={s} onDone={refresh} />)}
      </div>
      <p className="text-[11px] text-text-muted/70 mt-4">
        Approving imports the event. With deck lists it goes on the Top 8 page (tagged Local under 16 players);
        with no deck lists the placings go on players' profiles only. The player gets a Discord DM either way.
      </p>
      <div className="flex justify-end pt-3">
        <button className="text-xs px-3 py-1.5 rounded border border-border text-text-muted hover:text-text" onClick={onClose}>Close</button>
      </div>
    </Modal>
  )
}
