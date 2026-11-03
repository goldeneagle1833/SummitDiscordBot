import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { addArticleReviewer, getArticleReviewers, removeArticleReviewer } from '@/api/articles'
import PlayerPicker from '@/components/admin/PlayerPicker'

/**
 * Admins only, at the top of /articles: who reviews player articles.
 * Reviewers can approve articles on the site and get the bot's DMs.
 */
export default function ReviewersPanel() {
  const [data, setData] = useState(null)
  const [manualId, setManualId] = useState('')
  const [manualName, setManualName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const load = () => getArticleReviewers().then(setData).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const add = async (userId, username) => {
    setBusy(true)
    setError(null)
    try {
      await addArticleReviewer(String(userId).trim(), (username || '').trim())
      setManualId('')
      setManualName('')
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (r) => {
    if (!window.confirm(`Remove ${r.username} as a reviewer?`)) return
    setBusy(true)
    try {
      await removeArticleReviewer(r.user_id)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-lg border border-accent-red/40 bg-accent-red/5 p-4 space-y-3" aria-label="Article reviewers">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-bold text-text-primary">
            Reviewers <span className="ml-1 text-[11px] font-semibold uppercase tracking-wide text-red-300">Admins only</span>
          </h2>
          <p className="text-xs text-text-muted">Reviewers approve articles and get a Discord DM for each new one.</p>
        </div>
        <Link to="/admin/articles" className="text-sm text-secondary hover:underline">Open review queue →</Link>
      </div>

      {data && (
        <ul className="flex flex-wrap gap-2">
          {data.reviewers.map((r) => (
            <li key={r.user_id} className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-surface pl-3 pr-1 py-1 text-sm">
              <span>{r.username}</span>
              <button
                type="button"
                onClick={() => remove(r)}
                disabled={busy}
                className="w-6 h-6 rounded-full text-text-muted hover:text-red-400 hover:bg-accent-red/10"
                aria-label={`Remove ${r.username}`}
              >
                ×
              </button>
            </li>
          ))}
          {data.from_server_settings.map((id) => (
            <li key={id} className="inline-flex items-center gap-2 rounded-full border border-dashed border-border px-3 py-1 text-sm text-text-muted" title="Set in the server settings (ARTICLE_REVIEWER_IDS)">
              ID …{id.slice(-4)} <span className="text-[11px]">server setting</span>
            </li>
          ))}
          {data.reviewers.length === 0 && data.from_server_settings.length === 0 && (
            <li className="text-sm text-text-muted">No reviewers yet, so the admins get the DMs.</li>
          )}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <PlayerPicker label="Add a Summit player" onPick={(p) => add(p.user_id, p.display_name)} />
        <span className="text-xs text-text-muted">or by Discord ID:</span>
        <form
          onSubmit={(e) => { e.preventDefault(); if (manualId.trim()) add(manualId, manualName) }}
          className="flex flex-wrap items-center gap-2"
        >
          <input
            value={manualId}
            onChange={(e) => setManualId(e.target.value.replace(/\D/g, ''))}
            inputMode="numeric"
            placeholder="Discord user ID"
            aria-label="Discord user ID"
            className="h-9 w-44 rounded-lg border border-border bg-bg-raised px-3 text-sm"
          />
          <input
            value={manualName}
            onChange={(e) => setManualName(e.target.value)}
            placeholder="Name (optional)"
            aria-label="Reviewer name"
            maxLength={60}
            className="h-9 w-36 rounded-lg border border-border bg-bg-raised px-3 text-sm"
          />
          <button type="submit" disabled={busy || !manualId.trim()} className="h-9 px-3 rounded-lg border border-border text-sm hover:border-secondary disabled:opacity-40">
            Add
          </button>
        </form>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </section>
  )
}
